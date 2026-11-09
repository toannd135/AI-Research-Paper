import json
import re
from dataclasses import replace
from types import SimpleNamespace

from app.agent.evidence.consistency_check import check_consistency
from app.agent.evidence.external_verify import external_verify
from app.agent.evidence.extractor import BATCH_SIZE, extract_results, records_from_dicts, records_to_dicts
from app.agent.evidence.ledger import NR, render_ledger, replace_ledger
from app.agent.evidence.quant_analysis import (
    ablation_table,
    build_quant_blocks,
    efficiency_table,
    evidence_limits,
    inject_quant_blocks,
    missing_modality_table,
    modality_coverage_matrix,
    modality_degradation_chart,
    modality_matrix_stats,
    study_profile_table,
)
from app.agent.evidence.quant_check import ResultRecord
from app.agent.evidence.reference_check import CATALOG_MATCHED, CONFLICT, VERIFIED
from app.agent.evidence.study_profile import study_attributes
from app.agent.evidence.traceability import extract_numeric_claims
from app.agent.report_postprocess import postprocess_report
from app.pipeline.export import validation_gate


class _GW:
    def __init__(self, items):
        self.items, self.calls = items, 0

    def generate(self, messages, model_name=None):
        self.calls += 1
        return SimpleNamespace(text="Here:\n" + json.dumps(self.items), model="fake")


def _chunk(pid, page, text):
    return SimpleNamespace(chunk=SimpleNamespace(paper_id=pid, page=page, text=text))


EVIDENCE = [
    _chunk("pA", 5, "Table 2. BraTS 2020 validation. Ours Dice WT 90.5 TC 83.8 params 12.3"),
    _chunk("pB", 7, "BraTS 2020 validation Dice WT 88.1 TC 80.0 ET 70.2"),
]


def _item(**kw):
    base = {"paper_id": "pA", "model": "Ours", "dataset": "BraTS", "dataset_version": "2020", "split": "validation",
            "region": "WT", "metric": "Dice", "value": "90.5", "unit": "percent", "variant": None, "modality": None, "table": "Table 2"}
    return base | kw


# ---- P1 (deepfake: AUC/EER, không có region)
def test_extract_deepfake_metrics_without_region_and_eer_is_lower_better():
    from app.agent.evidence.stats import lower_is_better

    ev = [_chunk("pD", 6, "Table 3. Cross-dataset on Celeb-DF. Ours AUC 96.4 EER 8.7 acc 91.2")]
    items = [
        _item(paper_id="pD", dataset="Celeb-DF", dataset_version=None, split=None, region=None, metric="AUC", value="96.4", table="Table 3"),
        _item(paper_id="pD", dataset="Celeb-DF", dataset_version=None, split=None, region=None, metric="EER", value="8.7", table="Table 3"),
    ]
    recs = extract_results(ev, _GW(items))
    assert [(r.metric, r.region, r.value) for r in recs] == [("AUC", None, 96.4), ("EER", None, 8.7)]
    assert lower_is_better("EER") and not lower_is_better("AUC")


# ---- P1
def test_extract_keeps_only_values_verbatim_in_source_and_nulls_unseen_fields():
    items = [
        _item(),
        _item(value="99.9"),  # không có trong PDF → bỏ
        _item(model="Ours", region="TC", value="83.8", split="testing", dataset_version="2018", table="Table 9"),  # trường không thấy → None
        _item(paper_id="pZ"),  # paper không có evidence → bỏ
    ]
    recs = extract_results(EVIDENCE, _GW(items))
    assert [(r.region, r.value) for r in recs] == [("WT", 90.5), ("TC", 83.8)]
    assert recs[0].source_page == 5 and recs[0].source_table == "Table 2" and recs[0].dataset == "BraTS"
    assert recs[1].split is None and recs[1].dataset_version is None and recs[1].source_table is None


def test_extract_batches_and_survives_garbage():
    gw = _GW("not json")
    gw.generate = lambda messages, model_name=None: SimpleNamespace(text="oops", model="x")
    assert extract_results(EVIDENCE, gw) == []
    many = [_chunk(f"p{i}", 1, "Dice 90.5") for i in range(11)]
    gw2 = _GW([])
    extract_results(many, gw2)
    assert gw2.calls == -(-11 // BATCH_SIZE)  # ⌈11/BATCH_SIZE⌉


def test_records_roundtrip():
    recs = extract_results(EVIDENCE, _GW([_item()]))
    assert records_from_dicts(records_to_dicts(recs)) == recs


# ---- P2
def test_ledger_marks_missing_regions_nr_and_replaces_llm_ledger():
    recs = records_from_dicts(records_to_dicts(extract_results(EVIDENCE, _GW([_item(), _item(region="TC", value="83.8")]))))
    ledger = render_ledger(recs, {"pA": 1})
    assert "| [1] | Ours | BraTS 2020 | Dice ET | NR |" in ledger and "| Dice WT | 90.5 |" in ledger
    assert NR in render_ledger([], {}) or "No quantitative results" in render_ledger([], {})
    draft = "analysis\n\n## Quantitative Evidence Ledger\n| fake | row |\n"
    out = replace_ledger(draft, ledger)
    assert "fake" not in out and out.count("Quantitative Evidence Ledger") == 1


def test_export_blocked_when_gate_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(validation_gate, "get_settings", lambda: SimpleNamespace(upload_dir=str(tmp_path)))
    assert validation_gate.load_blocking("t1") == []
    (tmp_path / "validation").mkdir()
    (tmp_path / "validation" / "t1.json").write_text(json.dumps({"passed": False, "blocking": ["44 UNTRACED"]}))
    (tmp_path / "validation" / "t2.json").write_text(json.dumps({"passed": True, "blocking": []}))
    assert validation_gate.load_blocking("t1") == ["44 UNTRACED"]
    assert validation_gate.load_blocking("t2") == []


# ---- P3
_GOOD_ABSTRACT = " ".join(["word"] * 180) + " 90.5"


def test_consistency_catches_each_planted_error():
    text = (
        f"# T\n\n## Abstract\n{_GOOD_ABSTRACT} and 77.7\n\n## 1. Introduction\nRQ1 and RQ2 and RQ3.\n\n"
        "## 5. Evidence\n**Table 1:** a\n\n**Table 3:** b\n\n"
        '```table\n{"columns": ["Method", "Dataset"], "rows": [["Foo [1]", "BraTS2020"], ["FOO-Net [1]", "BraTS 2020"]]}\n```\n'
        "Formula $x^{2$ done.\n\n## 7. Conclusion\nRQ1 answered, RQ9 too.\n"
    )
    out = " | ".join(check_consistency(text))
    for needle in ("RQ[2, 3]", "RQ[9]", "tên method khác nhau", "dataset viết không nhất quán", "77.7", "Table caption", "ngoặc nhọn"):
        assert needle in out, needle
    assert "Abstract" not in out.split("77.7")[0] or "từ, ngoài" not in out  # 181 từ nằm trong 150–220


def test_consistency_clean_text_has_no_warnings():
    text = f"## Abstract\n{_GOOD_ABSTRACT}\n\n## 1. Introduction\nRQ1.\n\nBody 90.5.\n\n## 7. Conclusion\nRQ1 answered.\n"
    assert check_consistency(text) == []


# ---- P4
def _rec(model, pid, value, metric="Dice", region="WT", variant=None, unit="percent", split="validation"):
    return ResultRecord(paper_id=pid, model=model, dataset="BraTS", dataset_version="2020", split=split, region=region,
                        metric=metric, value=value, unit=unit, source_page=1, variant=variant)


def test_quant_blocks_only_when_comparable_and_enough():
    recs = [_rec("A", "p1", 90.0), _rec("B", "p2", 88.0), _rec("C", "p3", 85.5),
            _rec("A", "p1", 12.0, metric="Params", region=None, unit="M"), _rec("B", "p2", 30.0, metric="Params", region=None, unit="M"),
            _rec("C", "p3", 5.0, metric="Params", region=None, unit="M"),
            _rec("A", "p1", 87.0, variant="w/o X")]
    n = {"p1": 1, "p2": 2, "p3": 3}
    blocks = build_quant_blocks(recs, n)
    assert len(blocks) == 5 and "Evidence profile" in blocks[4]
    delta = json.loads(blocks[0].split("\n")[1])
    assert delta["derived"] and ["C [3]", "BraTS 2020 (validation)", "Dice WT", "85.5", "-4.50"] in delta["rows"]
    assert json.loads(blocks[1].split("\n")[1])["rows"][0][-1] == "-3.00"
    assert json.loads(blocks[2].split("\n")[1])["type"] == "scatter"
    eff = json.loads(blocks[3].split("\n")[1])
    assert eff["columns"] == ["Method [Ref]", "Params", "GFLOPs", "Inference time"] and ["A [1]", "12 M", "NR", "NR"] in eff["rows"]
    assert build_quant_blocks(recs[:2], n) == []  # <3 phương pháp → không sinh
    mixed = [_rec("A", "p1", 90.0), _rec("B", "p2", 88.0), _rec("C", "p3", 85.5, split="testing")]
    only = build_quant_blocks(mixed, n)  # khác split → không so sánh; chỉ còn bảng hồ sơ bằng chứng
    assert len(only) == 1 and "Evidence profile" in only[0]
    lower = [_rec(m, p, v, metric="HD95", unit="mm") for m, p, v in (("A", "p1", 5.0), ("B", "p2", 7.0), ("C", "p3", 4.0))]
    rows = json.loads(build_quant_blocks(lower, n)[0].split("\n")[1])["rows"]
    assert rows[0][0] == "C [3]" and rows[0][-1] == "+0.00" and rows[-1][-1] == "+3.00"  # HD95 thấp hơn = tốt hơn


def test_derived_blocks_survive_postprocess_and_skip_traceability():
    recs = [_rec("A", "p1", 90.0), _rec("B", "p2", 88.0), _rec("C", "p3", 85.5)]
    report = inject_quant_blocks("## 5. E\n\nText.\n\n### 5.5 X\n\nMore.\n\n## 6. D\n", build_quant_blocks(recs, {"p1": 1, "p2": 2, "p3": 3}))
    assert report.index("```table") < report.index("### 5.5")
    assert extract_numeric_claims(report) == []
    out = postprocess_report(report, "no ledger", None, None, "en")
    assert "-4.50" in out  # không bị scrub thành "–"


# ---- P5
def test_external_verify_upgrades_or_conflicts_without_network():
    catalog = {"a": {"title": "Attention Is All You Need", "doi": "10.1/x"}, "b": {"title": "Totally Different", "doi": "10.1/y"}, "c": {"title": "T", "doi": "10.1/z"}}
    mk = lambda pid: {"paper_id": pid, "status": CATALOG_MATCHED, "missing": [], "issues": []}  # noqa: E731
    refs = {"references": [mk("a"), mk("b"), mk("c")], "counts": {}}
    remote = {"10.1/x": {"title": ["Attention is all you need"]}, "10.1/y": {"title": ["Attention is all you need"]}}
    out = external_verify(refs, catalog, fetch=lambda doi: remote.get(doi))
    status = {r["paper_id"]: r["status"] for r in out["references"]}
    assert status == {"a": VERIFIED, "b": CONFLICT, "c": CATALOG_MATCHED}
    assert out["counts"] == {VERIFIED: 1, CONFLICT: 1, CATALOG_MATCHED: 1}
    assert re.search("Crossref", " ".join(out["references"][2]["issues"]))


def test_extract_runs_every_batch_and_retries_on_error(monkeypatch):
    from app.agent.evidence import extractor as ex
    from app.ai.llm_gateway.base import LLMGatewayError

    class _Flaky:
        calls = 0

        def generate(self, messages, model_name=None):
            self.calls += 1
            if self.calls == 1:
                raise LLMGatewayError("lỗi thoáng qua")
            return SimpleNamespace(text=json.dumps([_item()]), model="fake")

    many = [_chunk("pA" if i == 0 else f"p{i}", 5, "Dice WT 90.5 BraTS 2020 validation") for i in range(ex.BATCH_SIZE + 1)]
    gw = _Flaky()
    recs = ex.extract_results(many, gw)
    assert gw.calls == 3 and len(recs) == 1  # lô 1 lỗi → thử lại thành công; lô 2 vẫn chạy đủ

    class _AlwaysFail:
        calls = 0

        def generate(self, messages, model_name=None):
            self.calls += 1
            raise LLMGatewayError("hỏng")

    bad = _AlwaysFail()
    assert ex.extract_results(many, bad) == []
    assert bad.calls == 2 * ex.MAX_ATTEMPTS  # mọi lô đều được thử đủ số lần, không dừng giữa chừng

    # Hết ngân sách thời gian: bỏ các lô còn lại, trả về phần đã trích được.
    class _Ok:
        calls = 0

        def generate(self, messages, model_name=None):
            self.calls += 1
            return SimpleNamespace(text=json.dumps([_item()]), model="fake")

    ok = _Ok()
    assert ex.extract_results(many, ok, max_seconds=-1) == [] and ok.calls == 0


def _mrec(model, mods, value, paper="pA", region="WT", metric="Dice", split="validation"):
    return ResultRecord(paper_id=paper, model=model, dataset="BraTS", dataset_version="2018", split=split, region=region, metric=metric,
                        value=value, unit="percent", modality=tuple(mods), source_page=3)


FULL = ["T1", "T1ce", "T2", "FLAIR"]
MISSING_RECORDS = [
    _mrec("HeMIS", FULL, 80.0),
    _mrec("HeMIS", ["T1", "T2", "FLAIR"], 76.5),
    _mrec("HeMIS", ["T1ce", "FLAIR"], 74.0),
    _mrec("HeMIS", ["FLAIR"], 62.0),
    _mrec("Other", ["T1", "FLAIR"], 70.0, paper="pB"),
    _mrec("Other", ["FLAIR"], 60.0, paper="pB"),
]
P2N = {"pA": 1, "pB": 2}


def test_missing_modality_table_deltas_only_where_full_reported():
    table = json.loads(re.search(r"```table\n(.*)\n```", missing_modality_table(MISSING_RECORDS, P2N), re.S).group(1))
    assert table["derived"] is True
    rows = {(r[0], r[3]): r for r in table["rows"]}
    assert rows[("HeMIS [1]", "T1+T2+FLAIR")][5] == "-3.50"  # 76.5 - 80.0
    assert rows[("HeMIS [1]", "T1c+FLAIR")][5] == "-6.00"  # T1ce chuẩn hóa thành T1c
    assert rows[("HeMIS [1]", "Full (T1, T1c, T2, FLAIR)")][5] == "0.00"
    assert rows[("Other [2]", "FLAIR")][5] == "n/r"  # nguồn không báo full -> không suy diễn


def test_modality_chart_is_delta_heatmap_with_nr_cells():
    block = modality_degradation_chart(MISSING_RECORDS, P2N)
    spec = json.loads(re.search(r"```chart\n(.*)\n```", block, re.S).group(1))
    assert spec["type"] == "heatmap" and spec["derived"] is True
    assert spec["x_labels"] == ["HeMIS [1] (full 80)"]  # "Other" không có mốc full → không tính Δ
    assert len(spec["y_labels"]) == 14  # mọi tập thiếu modality, kể cả tập không báo cáo
    deltas = {y: row[0] for y, row in zip(spec["y_labels"], spec["matrix"], strict=True)}
    assert sorted(v for v in deltas.values() if v is not None) == [-18.0, -6.0, -3.5]
    assert sum(v is None for v in deltas.values()) == 11  # NR, không nội suy
    assert "not comparable" in spec["caption"]


def test_modality_blocks_absent_when_no_modality_records():
    plain = [_mrec("X", [], 70.0), _mrec("Y", [], 71.0)]
    assert missing_modality_table(plain, P2N) is None and modality_degradation_chart(plain, P2N) is None
    assert modality_matrix_stats(plain, P2N)["groups"] == 0


def test_unknown_modality_name_is_not_guessed():
    recs = [_mrec("Z", ["T1", "weird"], 50.0), _mrec("Z", ["T1"], 40.0)]
    assert missing_modality_table(recs, P2N) is None


def test_evidence_limits_states_real_gaps():
    none_text = evidence_limits([_mrec("X", [], 70.0)], P2N, 2)
    assert "No missing-modality result" in none_text and "Do NOT write that no source reports" in none_text
    assert "no standard deviation" in none_text
    some_text = evidence_limits(MISSING_RECORDS, P2N, 2)
    assert "WERE extracted from 2 source(s) (2 method/setting groups, 1 with the same source's full-modality result" in some_text
    assert "of the 15 non-empty modality subsets" in some_text and "setting(s) shared by ≥2 sources" in some_text
    assert "carry NO citation" in some_text


# Lỗi thật ở survey_58ad3caf: extractor ghi "Missing T1c" vào variant → EVIDENCE LIMITS nói "không nguồn nào báo"
# trong khi bảng ablation lại có các dòng thiếu modality.
ABLATED = [
    ResultRecord(paper_id="pA", model="Proposed", dataset="BraTS", dataset_version="2018", split="validation", region=reg,
                 metric="Dice", value=v, unit="ratio", source_page=6, variant=var)
    for reg, var, v in (("WT", None, 0.894), ("WT", "Missing T1c", 0.879), ("WT", "Missing Flair", 0.616),
                        ("ET", None, 0.653), ("ET", "w/o T1ce", 0.484), ("ET", "Missing T1 and T2", 0.60))
]


def test_missing_modality_variants_become_subsets_not_ablation_rows():
    stats = modality_matrix_stats(ABLATED, P2N)
    assert stats["groups"] == 2 and stats["groups_with_full"] == 2 and stats["sources"] == 1
    assert "T1+T2+FLAIR" in stats["subset_labels"] and "T1c+FLAIR" in stats["subset_labels"]
    table = json.loads(re.search(r"```table\n(.*)\n```", missing_modality_table(ABLATED, P2N), re.S).group(1))
    rows = {(r[2], r[3]): r[5] for r in table["rows"]}
    assert rows[("Dice WT", "T1+T1c+T2")] == "-0.28" and rows[("Dice ET", "T1+T2+FLAIR")] == "-0.17"
    assert ablation_table(ABLATED, P2N) is None  # không lặp lại trong bảng ablation
    assert "No missing-modality result" not in evidence_limits(ABLATED, P2N, 1)


def test_unrecognised_variant_is_not_treated_as_missing_modality():
    recs = [replace(ABLATED[0]), replace(ABLATED[1], variant="Missing decoder skip")]
    assert modality_matrix_stats(recs, P2N)["groups"] == 0 and ablation_table(recs, P2N) is not None


def test_study_profile_table_uses_verbatim_sentences_and_nr():
    n = {"p1": 1, "p2": 2, "p3": 3}
    recs = [_rec("A", "p1", 90.0), _rec("B", "p2", 88.0), replace(_rec("C", "p3", 85.5), spread=1.2, spread_type="SD")]
    evidence = [
        _chunk("p1", 4, "We evaluate on an external test cohort from two hospitals. The code is publicly available at https://github.com/x/y."),
        _chunk("p2", 2, "Smith et al. used five-fold cross-validation [7]. Our model is not validated on an external dataset."),
        _chunk("p3", 6, "We adopt a five-fold cross-validation with a patient-wise split. Modalities are randomly dropped during training."),
    ]
    attrs = study_attributes(evidence)
    assert "cross_validation" not in attrs.get("p2", {})  # câu nói về công trình khác (et al., [7]) bị bỏ
    assert attrs["p2"]["external_validation"]["value"] == "No"
    spec = json.loads(re.search(r"```table\n(.*)\n```", study_profile_table(recs, n, attrs), re.S).group(1))
    rows = {r[0]: dict(zip(spec["columns"], r, strict=True)) for r in spec["rows"]}
    assert rows["[1]"]["External validation"] == "Yes (p. 4)" and rows["[1]"]["Code available"] == "Yes (p. 4)"
    assert rows["[1]"]["Cross-validation"] == "NR" and rows["[2]"]["External validation"] == "No (p. 2)"
    assert rows["[3]"]["Patient-wise split"] == "Yes (p. 6)" and rows["[3]"]["Missing-modality protocol"] == "Random dropout (p. 6)"
    assert rows["[3]"]["Variance reported"].startswith("Yes") and "does not mean the study did not do it" in spec["caption"]
    assert study_profile_table(recs[:2], n) is None
    limits = evidence_limits(recs, n, 3, attrs)
    assert "external/multi-centre validation 1" in limits and "patient-wise split 1" in limits


def test_modality_variant_spellings_and_multi_missing():
    from app.agent.evidence.quant_analysis import _variant_modalities as v

    assert v("Missing T1 post-contrast") == frozenset({"T1", "T2", "FLAIR"})
    assert v("w/o T1 and T2") == frozenset({"T1c", "FLAIR"})
    assert v("missing T1, T2, FLAIR") == frozenset({"T1c"})
    assert v("FLAIR only") == v("only FLAIR") == frozenset({"FLAIR"})
    assert v("available: T1ce + FLAIR") == frozenset({"T1c", "FLAIR"})
    assert v("without T1+C") == frozenset({"T1", "T2", "FLAIR"})  # T1+C là một modality
    assert v("Missing T1, T1c, T2, FLAIR") is None and v("w/o decoder") is None and v("missing T3") is None


def test_coverage_matrix_has_15_rows_nr_and_setting_letters():
    spec = json.loads(re.search(r"```table\n(.*)\n```", modality_coverage_matrix(ABLATED, P2N), re.S).group(1))
    assert len(spec["rows"]) == 16 and spec["rows"][-1][0] == "Subsets reported"
    rows = {r[0]: r[1:] for r in spec["rows"]}
    assert rows["T1+T2+FLAIR"] == ["0.484 (-0.169)", "0.879 (-0.015)"]
    assert rows["FLAIR"] == ["NR", "NR"] and rows["Subsets reported"] == ["3/15", "3/15"]
    assert spec["columns"][1].endswith("· A") and spec["columns"][2].endswith("· B")
    assert "not comparable" in spec["caption"] and "no cell is imputed" in spec["caption"]

def test_build_quant_blocks_includes_modality_blocks():
    blocks = build_quant_blocks(MISSING_RECORDS, P2N)
    assert any("Available modalities" in b for b in blocks) and any("Missing-modality robustness" in b for b in blocks)


# ---- Spread (SD/SE/CI) và bảng hiệu năng tính toán
def _spread_evidence(text):
    return [_chunk("pA", 5, text)]


def test_extract_keeps_spread_only_when_printed_after_plusminus_with_valid_type():
    ev = _spread_evidence("BraTS 2020 validation Dice WT 90.5 ± 2.1 (SD) and 83.8 +/- 1.0")
    keep = extract_results(ev, _GW([_item(spread="2.1", spread_type="SD")]))[0]
    assert (keep.spread, keep.spread_type) == (2.1, "SD")
    invented = extract_results(ev, _GW([_item(spread="9.9", spread_type="SD")]))[0]
    assert invented.spread is None and invented.spread_type is None  # 9.9 không đứng sau ±
    untyped = extract_results(ev, _GW([_item(spread="2.1", spread_type="range")]))[0]
    assert untyped.spread is None  # loại sai số lạ → bỏ, không đoán
    assert extract_results(ev, _GW([_item(spread="2.1", spread_type="std")]))[0].spread_type == "SD"


def test_old_records_without_spread_still_load():
    old = {k: v for k, v in records_to_dicts(extract_results(EVIDENCE, _GW([_item()])))[0].items() if k not in ("spread", "spread_type")}
    assert records_from_dicts([old])[0].spread is None


def test_delta_table_adds_spread_column_only_when_reported():
    n = {"p1": 1, "p2": 2, "p3": 3}
    recs = [_rec("A", "p1", 90.0), _rec("B", "p2", 88.0), _rec("C", "p3", 85.5)]
    assert "Spread" not in json.loads(build_quant_blocks(recs, n)[0].split("\n")[1])["columns"]
    with_sd = [replace(recs[0], spread=2.1, spread_type="SD"), *recs[1:]]
    table = json.loads(build_quant_blocks(with_sd, n)[0].split("\n")[1])
    assert table["columns"][-1] == "Spread" and table["rows"][0][-1] == "±2.1 (SD)" and table["rows"][1][-1] == "NR"


def test_efficiency_table_needs_two_methods_and_marks_missing_nr():
    n = {"p1": 1, "p2": 2}
    one = [_rec("A", "p1", 12.0, metric="Params", region=None, unit="M")]
    assert efficiency_table(one, n) is None
    two = [*one, _rec("B", "p2", 3.2, metric="InferenceTime", region=None, unit="ms"), _rec("B", "p2", 30.0, metric="GFLOPs", region=None, unit="G")]
    rows = json.loads(efficiency_table(two, n).split("\n")[1])["rows"]
    assert rows == [["A [1]", "12 M", "NR", "NR"], ["B [2]", "NR", "30 G", "3.2 ms"]]


def test_evidence_limits_reports_real_spread_count_and_ledger_shows_it():
    rec = replace(_mrec("X", [], 70.0), spread=1.5, spread_type="CI95")
    assert "only 1 of them report a spread" in evidence_limits([rec], P2N, 2)
    assert "±1.5 (CI95)" in render_ledger([rec], P2N)


def test_consistency_warns_on_mixed_dice_scale():
    mixed_pipe = "**Table 3: Results**\n\n| Method | Dice WT |\n|---|---|\n| nnU-Net [1] | 82.03 |\n| Swin UNETR [2] | 0.891 |\n"
    assert any("trộn Dice" in w for w in check_consistency(mixed_pipe))
    per_row = '```table\n{"caption": "T", "columns": ["Method", "Metric", "Value"], "rows": [["A", "Dice WT", "0.89"], ["B", "Dice WT", "72.9"], ["C", "HD95", "4.1"]]}\n```'
    assert any("trộn Dice" in w for w in check_consistency(per_row))
    same_scale = '```table\n{"caption": "T", "columns": ["Method", "Metric", "Value"], "rows": [["A", "Dice WT", "89.1"], ["C", "HD95", "4.1"]]}\n```'
    assert not any("trộn Dice" in w for w in check_consistency(same_scale))


def test_extract_results_dung_cache_theo_lo(monkeypatch):
    """Chạy lại cùng evidence thì không gọi LLM nữa; kết quả vẫn được kiểm chứng lại như cũ."""
    monkeypatch.setattr("app.agent.evidence.extractor.CACHE_ENABLED", True)
    first = extract_results(EVIDENCE, _GW([_item()]))
    second = extract_results(EVIDENCE, _GW([]))  # gateway rỗng: nếu gọi LLM sẽ không ra bản ghi nào
    assert first and second == first


def test_evidence_limits_counts_papers_with_records_not_cited_papers():
    """Bản thảo c5d84302 viết '417 records from 40 papers' vì n_papers là số paper được cite, không phải số paper có bản ghi."""
    text = evidence_limits([_mrec("X", [], 70.0)], P2N, 2)
    assert "from 1 of the 2 cited papers" in text and "the other 1 contributed no record" in text
    assert "never call it exhaustive" in text


def test_evidence_limits_zero_subset_count_means_not_observed():
    """Số đếm 0 từ regex trên đoạn truy xuất phải được diễn đạt là 'không thấy', không phải 'không nghiên cứu nào'."""
    text = evidence_limits(MISSING_RECORDS, P2N, 2, {"pA": {}})
    assert "not observed in the retrieved passages" in text and "never 'no study does this'" in text
    assert "no method/setting group with all 15 subsets" in text
