import json
import re

from app.agent.evidence.evidence_tiers import (
    DIRECT,
    OTHER_DATASET,
    REFERENCE_ONLY,
    classify_evidence,
    dataset_family,
    target_family,
    tiers_fact,
)
from app.agent.evidence.quant_analysis import study_profile_table
from app.agent.evidence.quant_check import ResultRecord


def _rec(pid, dataset, value=90.0, model="M"):
    return ResultRecord(paper_id=pid, model=model, dataset=dataset, dataset_version=None, split="validation", region="WT",
                        metric="Dice", value=value, unit="percent", source_page=1)


RECS = [_rec("p1", "BraTS 2021"), _rec("p2", "BraTS-2020 challenge"), _rec("p3", "FeTA 2021"), _rec("p4", "FLARE"), _rec("p5", "BraTS2019")]


def test_dataset_family_strips_years_and_noise():
    assert dataset_family("BraTS 2021") == dataset_family("BraTS-2020 challenge") == dataset_family("BraTS2019") == "brats"
    assert dataset_family("FeTA 2021") == "feta"
    assert dataset_family(None) is None


def test_target_prefers_question_then_majority():
    assert target_family(RECS, "Missing-modality robustness on FeTA")[0] == "feta"
    assert target_family(RECS, "Brain tumor segmentation")[0] == "brats"
    assert target_family([_rec("a", "FeTA"), _rec("b", "FLARE")], "")[0] is None  # hòa → không đoán


def test_classify_and_fact_separate_three_tiers():
    cited = ["p1", "p2", "p3", "p4", "p6"]
    c = classify_evidence(RECS, cited, "Brain tumor segmentation")
    assert c["tiers"] == {"p1": DIRECT, "p2": DIRECT, "p3": OTHER_DATASET, "p4": OTHER_DATASET, "p6": REFERENCE_ONLY}
    n = {p: i for i, p in enumerate(cited, start=1)}
    fact = tiers_fact(c, n)
    assert "Direct evidence (results reported on BraTS 2021): [1], [2]" in fact
    assert "[3] FeTA 2021; [4] FLARE" in fact
    assert "Architectural reference only (no extracted quantitative result): [5]" in fact
    assert tiers_fact({"target": None, "tiers": {}}, n) == ""


def test_profile_table_marks_other_dataset_rows():
    n = {"p1": 1, "p2": 2, "p3": 3}
    recs = RECS[:3]
    tiers = classify_evidence(recs, n, "brain tumor")["tiers"]
    spec = json.loads(re.search(r"```table\n(.*)\n```", study_profile_table(recs, n, None, tiers), re.S).group(1))
    rows = {r[0]: r[1] for r in spec["rows"]}
    assert rows["[3]"] == "FeTA 2021 (other dataset)" and rows["[1]"] == "BraTS 2021"
    assert "indirect evidence" in spec["caption"]
