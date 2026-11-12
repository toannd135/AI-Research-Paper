"""Ba chế độ (chung / MRI não / deepfake) không được lẫn prompt hay kiểm tra của nhau."""

import json
import re

import pytest

from app.agent import domains
from app.agent.domains import DEEPFAKE, GENERAL, MRI_BRAIN, set_domain


def _structure_text():
    from app.agent.nodes.synthesize_node import _STAGE_STRUCTURES, _domain_stage

    return _domain_stage("\n".join(body for _, body in _STAGE_STRUCTURES["survey"].values()))


def test_unknown_domain_falls_back_to_general():
    set_domain("abc")
    assert domains.current_domain() == GENERAL
    set_domain("MRI-Brain")
    assert domains.current_domain() == MRI_BRAIN


def test_general_has_no_mri_or_deepfake_prompt_text():
    set_domain(GENERAL)
    text = (domains.extract_profile()["prompt"] + domains.domain_rules() + _structure_text()).lower()
    for word in ("tumor", "wt/tc/et", "dice", "hd95", "flair", "clinical", "deepfake", "cross-generator", "celeb-df"):
        assert not re.search(rf"\b{re.escape(word)}\b", text), word
    assert domains.extract_profile()["regions"] == {}


def test_mri_prompts_only_mri():
    set_domain(MRI_BRAIN)
    text = (domains.extract_profile()["prompt"] + domains.domain_rules() + _structure_text()).lower()
    assert "dice" in text and "whole tumor" in text and "clinical" in text
    for word in ("deepfake", "cross-generator", "celeb-df", "faceforensics", "eer"):
        assert not re.search(rf"\b{re.escape(word)}\b", text), word


def test_deepfake_prompts_only_deepfake():
    set_domain(DEEPFAKE)
    text = (domains.extract_profile()["prompt"] + domains.domain_rules() + _structure_text()).lower()
    assert "deepfake" in text and "eer" in text and "cross-generator" in text
    for word in ("tumor", "dice", "hd95", "flair", "t1c", "brats", "clinical"):
        assert not re.search(rf"\b{re.escape(word)}\b", text), word
    assert domains.extract_profile()["regions"] == {}


@pytest.mark.parametrize("domain", [GENERAL, DEEPFAKE])
def test_terms_are_scoped(domain):
    from app.agent.evidence.science_qa import check_terminology

    set_domain(domain)
    out = " ".join(check_terminology("tumor and tumour; T1c and T1ce; deepfake and deep-fakes; cross-generator and cross generator."))
    assert "tumo" not in out and "T1c" not in out
    assert ("deepfake" in out) == (domain == DEEPFAKE)


def test_mri_terms_not_flagged_in_deepfake_but_flagged_in_mri():
    from app.agent.evidence.science_qa import check_terminology

    text = "tumor and tumour, deepfake and deep-fakes."
    set_domain(MRI_BRAIN)
    out = " ".join(check_terminology(text))
    assert "tumo" in out and "deepfake" not in out


def test_chart_region_check_only_in_mri():
    from app.agent.evidence.quant_check import check_chart_block

    spec = json.dumps({"caption": "Dice on WT and TC", "series": [{"name": "WT"}, {"name": "TC"}]})
    set_domain(GENERAL)
    assert not any("vùng" in p for p in check_chart_block(spec))
    set_domain(MRI_BRAIN)
    assert any("vùng" in p for p in check_chart_block(spec))


# ---------- khung bài riêng theo chế độ ----------
from app.agent.evidence.quant_check import ResultRecord  # noqa: E402


def _stage4(domain, field=None):
    from app.agent.nodes.synthesize_node import _stage_structure

    set_domain(domain)
    state = {"question": "q", "audience": "lecturer", "field": field or domains.domain_field() or "computing"}
    return _stage_structure(state, "survey", "stage4")[1]


def test_domain_locks_field():
    set_domain(MRI_BRAIN)
    assert domains.domain_field() == "medicine"
    set_domain(DEEPFAKE)
    assert domains.domain_field() == "computer_vision"
    set_domain(GENERAL)
    assert domains.domain_field() is None


def test_plan_node_uses_domain_field_over_llm_guess():
    import importlib

    pn = importlib.import_module("app.agent.nodes.plan_node")
    from pathlib import Path

    src = Path(pn.__file__).read_text(encoding="utf-8")
    assert "domain_field()" in src  # thứ tự ưu tiên: người dùng > chế độ > LLM


def test_stage4_templates_differ_per_domain():
    general, mri, fake = _stage4(GENERAL), _stage4(MRI_BRAIN), _stage4(DEEPFAKE)
    assert "Missing-Modality Robustness" in mri and "Clinical Evidence Summary" in mri
    assert "Cross-Dataset & Cross-Generator Generalization" in fake and "Robustness to Compression" in fake
    assert "Missing-Modality" not in general + fake and "Cross-Generator" not in general + mri
    # lĩnh vực computer_vision không được nhân đôi mục 'Qualitative Visual Comparison' (đã có 5.3)
    assert len(re.findall(r"^###.*Qualitative Visual Comparison", fake, re.M)) == 1


def _r(model, pid, value, metric="AUC", dataset="Celeb-DF", split="cross-dataset", unit="percent", region=None):
    return ResultRecord(paper_id=pid, model=model, dataset=dataset, dataset_version=None, split=split, region=region,
                        metric=metric, value=value, unit=unit, source_page=1)


def _deepfake_records():
    recs = []
    for i, (m, pid) in enumerate([("Xception", "p1"), ("F3Net", "p2"), ("SBI", "p3")]):
        recs.append(_r(m, pid, 99.0 - i, dataset="FF++", split="in-domain"))
        recs.append(_r(m, pid, 70.0 + i, dataset="Celeb-DF", split="cross-dataset"))
        recs.append(_r(m, pid, 20.0 + i, metric="Params", dataset="FF++", split="in-domain", unit="M"))
    return recs, {"p1": 1, "p2": 2, "p3": 3}


def test_cross_dataset_table_only_in_deepfake():
    from app.agent.evidence.quant_analysis import build_quant_blocks, cross_dataset_table

    recs, p2n = _deepfake_records()
    set_domain(DEEPFAKE)
    table = cross_dataset_table(recs, p2n)
    spec = json.loads(table.split("\n", 1)[1].rsplit("```", 1)[0])
    assert spec["columns"][0] == "Method [Ref]" and any("Celeb-DF (cross-dataset" in c for c in spec["columns"])
    assert len(spec["rows"]) == 3 and all("NR" not in row for row in spec["rows"])
    assert any("Celeb-DF (cross-dataset" in b for b in build_quant_blocks(recs, p2n))
    set_domain(GENERAL)
    assert not any("cross-dataset, percent" in b for b in build_quant_blocks(recs, p2n))


def test_tradeoff_scatter_uses_domain_metric():
    from app.agent.evidence.quant_analysis import tradeoff_scatter

    recs, p2n = _deepfake_records()
    recs.append(_r("RECCE", "p4", 96.0, dataset="FF++", split="in-domain"))
    recs.append(_r("RECCE", "p4", 25.0, metric="Params", dataset="FF++", split="in-domain", unit="M"))
    p2n["p4"] = 4
    set_domain(DEEPFAKE)
    chart = tradeoff_scatter(recs, p2n)
    assert chart and "AUC versus parameter count" in chart and "None" not in chart and "Dice" not in chart
    set_domain(MRI_BRAIN)
    assert tradeoff_scatter(recs, p2n) is None  # MRI chỉ vẽ Dice theo vùng


def test_delta_table_has_no_none_region():
    from app.agent.evidence.quant_analysis import delta_table

    recs, p2n = _deepfake_records()
    set_domain(DEEPFAKE)
    table = delta_table(recs, p2n)
    assert table and "None" not in table


def test_profile_table_columns_per_domain():
    from app.agent.evidence.quant_analysis import study_profile_table

    recs, p2n = _deepfake_records()
    attrs = {"p1": {"unseen_generator": {"value": "Yes", "page": 3, "quote": "x"}}}
    set_domain(DEEPFAKE)
    fake = json.loads(study_profile_table(recs, p2n, attrs).split("\n", 1)[1].rsplit("```", 1)[0])
    assert "Cross-dataset test" in fake["columns"] and "Patient-wise split" not in fake["columns"]
    assert all(len(r) == len(fake["columns"]) for r in fake["rows"])
    assert fake["rows"][0][fake["columns"].index("Unseen generator / manipulation")] == "Yes (p. 3)"
    set_domain(MRI_BRAIN)
    mri = json.loads(study_profile_table(recs, p2n, attrs).split("\n", 1)[1].rsplit("```", 1)[0])
    assert "Patient-wise split" in mri["columns"] and "Cross-dataset test" not in mri["columns"]
    set_domain(GENERAL)
    gen = json.loads(study_profile_table(recs, p2n, attrs).split("\n", 1)[1].rsplit("```", 1)[0])
    assert "Patient-wise split" not in gen["columns"] and "Cross-dataset test" not in gen["columns"]
    assert all(len(r) == len(gen["columns"]) for r in gen["rows"])


def test_study_attributes_detects_deepfake_protocols():
    from types import SimpleNamespace

    from app.agent.evidence.study_profile import study_attributes

    ev = [SimpleNamespace(paper_id="p1", page=4, text="We train on FF++ and test on Celeb-DF. Our model is robust to compression at c40.")]
    attrs = study_attributes(ev)["p1"]
    assert attrs["cross_dataset_eval"]["value"] == "Yes" and attrs["compression_robustness"]["value"] == "Yes"


def test_results_query_uses_domain_metrics():
    import importlib

    sn = importlib.import_module("app.agent.nodes.search_node")
    set_domain(MRI_BRAIN)
    assert "Dice" in sn._results_query({"field": "medicine"}, "glioma")
    set_domain(DEEPFAKE)
    q = sn._results_query({"field": "computer_vision"}, "deepfake")
    assert "EER" in q and "Dice" not in q
    set_domain(GENERAL)
    assert "Dice" not in sn._results_query({"field": "computing"}, "llm")
