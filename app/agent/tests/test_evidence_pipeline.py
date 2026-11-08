import json
import re
from types import SimpleNamespace

from app.agent.evidence.consistency_check import check_consistency
from app.agent.evidence.external_verify import external_verify
from app.agent.evidence.extractor import BATCH_SIZE, extract_results, records_from_dicts, records_to_dicts
from app.agent.evidence.ledger import NR, render_ledger, replace_ledger
from app.agent.evidence.quant_analysis import build_quant_blocks, inject_quant_blocks
from app.agent.evidence.quant_check import ResultRecord
from app.agent.evidence.reference_check import CATALOG_MATCHED, CONFLICT, VERIFIED
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
    assert len(blocks) == 3
    delta = json.loads(blocks[0].split("\n")[1])
    assert delta["derived"] and ["C [3]", "BraTS 2020 (validation)", "Dice WT", "85.5", "-4.50"] in delta["rows"]
    assert json.loads(blocks[1].split("\n")[1])["rows"][0][-1] == "-3.00"
    assert json.loads(blocks[2].split("\n")[1])["type"] == "scatter"
    assert build_quant_blocks(recs[:2], n) == []  # <3 phương pháp → không sinh
    mixed = [_rec("A", "p1", 90.0), _rec("B", "p2", 88.0), _rec("C", "p3", 85.5, split="testing")]
    assert build_quant_blocks(mixed, n) == []  # khác split → không so sánh
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
