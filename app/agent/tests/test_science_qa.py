"""Scientific Consistency QA: mỗi luật có một ca bắt lỗi và một ca hợp lệ (không báo nhầm)."""

from app.agent.evidence.quant_check import ResultRecord
from app.agent.evidence.science_qa import (
    check_absence_claims,
    check_nr_legend,
    check_overclaims,
    check_scope,
    check_taxonomy_membership,
    check_terminology,
    run_science_qa,
)


def _r(variant=None, value=0.9, spread=None):
    return ResultRecord(paper_id="pA", model="M", dataset="BraTS", dataset_version="2018", split="validation", region="WT",
                        metric="Dice", value=value, unit="ratio", source_page=3, variant=variant, spread=spread,
                        spread_type="SD" if spread else None)


ABLATION = [_r(), _r("Missing FLAIR", 0.6), _r("Missing T1c", 0.85)]
P2N = {"pA": 4}


def test_absence_claim_contradicting_records_is_flagged():
    text = "## 5. Evidence\n\nNo source reports per-modality degradation, so it cannot be quantified [4].\n"
    assert check_absence_claims(text, ABLATION, P2N, {})
    assert check_absence_claims(text, [_r()], P2N, {}) == []  # thật sự không có record thiếu modality → đúng


def test_qualified_absence_and_unrelated_negation_are_not_flagged():
    text = (
        "No complete matrix over all 15 subsets can be built from the corpus.\n"
        "Neither offers a taxonomy of missing-modality handling.\n"
    )
    assert check_absence_claims(text, ABLATION, P2N, {}) == []


def test_absence_of_external_validation_contradicting_sentence_evidence():
    attrs = {"pA": {"external_validation": {"value": "Yes", "page": 5, "quote": "We test on an external cohort."}}}
    text = "None of the studies performs external validation on independent cohorts.\n"
    assert any("external validation" in w for w in check_absence_claims(text, [], P2N, attrs))


def test_terminology_mixed_forms():
    assert check_terminology("T1ce is key. FLAIR too. Later T1c is used.\n\n## References\n[1] T1Gd paper")
    assert check_terminology("T1c only. T1c again.\n\n## References\n[1] about T1ce") == []  # References không tính


def test_scope_year_beyond_latest_reference():
    text = "# Survey of X (2015–2025)\n\n## Abstract\nWe cover work up to 2025.\n\n## References\n[1] A, \"T\", 2021.\n[2] B, 2023.\n"
    assert check_scope(text)
    assert check_scope(text.replace("2025", "2023")) == []


def test_overclaims_in_abstract_and_conclusion():
    text = (
        "## Abstract\nTransformers significantly outperform CNNs.\n\n## 4. Body\nX outperforms Y.\n\n"
        "## 7. Conclusion\nHybrid models are state-of-the-art.\nUnder the same protocol, A outperforms B [3].\n"
    )
    out = check_overclaims(text, [_r()])
    assert len(out) == 2 and "abstract" in out[0] and "conclusion" in out[1]
    assert not any("significant" in w for w in check_overclaims("## Abstract\nA significant gain was reported.\n", [_r(spread=0.01)]))


def test_taxonomy_source_in_two_categories_of_same_axis():
    text = (
        "**Table 2: Taxonomy of methods**\n\n| Axis | Category | Refs |\n|---|---|---|\n"
        "| Architecture | Transformer | [7], [12] |\n| | Hybrid CNN-Transformer | [7] |\n| Fusion | Input-level | [7] |\n"
    )
    out = check_taxonomy_membership(text)
    assert len(out) == 1 and "[7]" in out[0] and "Architecture" in out[0]


def test_nr_needs_definition():
    bad = '```table\n{"caption": "Results", "columns": ["A", "B"], "rows": [["x", "NR"]]}\n```\n'
    good = '```table\n{"caption": "Results (NR = not reported)", "columns": ["A", "B"], "rows": [["x", "NR"]]}\n```\n'
    assert check_nr_legend(bad) and check_nr_legend(good) == []


def test_run_science_qa_clean_text_has_no_warnings():
    text = "## Abstract\nWe review fusion methods reported in [1].\n\n## 7. Conclusion\nEvidence remains limited.\n\n## References\n[1] A, 2024.\n"
    assert run_science_qa(text, ABLATION, P2N, {}) == []
