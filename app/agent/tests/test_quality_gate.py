"""Quality Gate: tính so sánh được, xác minh tham khảo, truy vết số liệu, gate tổng hợp."""

import json
from dataclasses import replace
from types import SimpleNamespace

from app.agent.evidence import quant_check as q
from app.agent.evidence.consistency_check import check_review_claims
from app.agent.evidence.display_check import check_figure_captions
from app.agent.evidence.quality_gate import merge_structure_issues, run_quality_gate
from app.agent.evidence.reference_check import (
    CATALOG_MATCHED,
    CONFLICT,
    INVALID,
    PARTIALLY_VERIFIED,
    UNVERIFIED,
    classify_publication,
    verify_references,
)
from app.agent.evidence.traceability import NO_CITATION, TRACED, UNTRACED, extract_numeric_claims, trace_claims

BASE = q.ResultRecord(
    paper_id="p1", model="A", dataset="BraTS", dataset_version="BraTS 2021", split="validation", region="ET",
    metric="Dice", value=0.9, unit="ratio", modality=("T1", "T1ce", "T2", "FLAIR"), preprocessing="z-score",
    source_page=8, source_table="Table 3",
)


def _other(**kw):
    return replace(BASE, paper_id="p2", model="B", value=0.85, **kw)


def test_same_protocol_is_comparable():
    assert q.compare(BASE, _other())[0] == q.COMPARABLE


def test_different_region_version_split_metric_are_rejected():
    assert q.compare(BASE, _other(region="WT"))[0] == q.NOT_COMPARABLE
    assert q.compare(BASE, _other(dataset_version="BraTS 2020"))[0] == q.NOT_COMPARABLE
    assert q.compare(BASE, _other(split="test"))[0] == q.NOT_COMPARABLE
    assert q.compare(BASE, _other(metric="HD95", unit="mm"))[0] == q.NOT_COMPARABLE


def test_missing_information_is_unverified_not_guessed():
    status, reasons = q.compare(BASE, _other(dataset_version=None))
    assert status == q.UNVERIFIED and any("phiên bản" in r for r in reasons)
    assert q.compare(BASE, _other(split=None))[0] == q.UNVERIFIED


def test_different_modality_or_preprocessing_is_conditional():
    assert q.compare(BASE, _other(modality=("T1ce", "FLAIR")))[0] == q.CONDITIONALLY_COMPARABLE
    assert q.compare(BASE, _other(preprocessing=None))[0] == q.CONDITIONALLY_COMPARABLE


def test_value_without_pdf_source_is_rejected():
    no_source = _other(source_page=None, source_table=None)
    assert q.compare(BASE, no_source)[0] == q.NOT_COMPARABLE
    assert any("nguồn" in p for p in q.validate_record(no_source))


def test_record_range_and_unit_checks():
    assert q.validate_record(replace(BASE, value=1.2))  # Dice ratio > 1
    assert q.validate_record(replace(BASE, unit=None))  # thiếu đơn vị gốc, không tự đổi
    assert not q.validate_record(replace(BASE, value=91.2, unit="percent"))
    assert q.compare(BASE, _other(unit="percent"))[0] == q.NOT_COMPARABLE  # không tự chuyển % ↔ tỷ lệ
    assert q.validate_record(replace(BASE, metric="HD95", unit="mm", value=-1.0))


def test_group_comparable_separates_unverified_and_rejected():
    out = q.group_comparable([BASE, _other(), _other(region=None), replace(BASE, value=3.0)])
    assert len(out["groups"]) == 1 and len(next(iter(out["groups"].values()))) == 2
    assert len(out["unverified"]) == 1 and len(out["rejected"]) == 1
    cond = q.group_comparable([BASE, _other(preprocessing="other")])
    assert len(cond["conditional"]) == 1


def test_chart_block_rejects_mixed_regions_and_metrics():
    mixed = json.dumps({"type": "bar", "caption": "Dice (source [1])", "labels": ["A"], "series": [{"name": "WT Dice", "values": [0.9]}, {"name": "ET Dice", "values": [0.8]}]})
    assert q.check_chart_block(mixed)
    ok = json.dumps({"type": "bar", "caption": "ET Dice [1]", "labels": ["A", "B"], "series": [{"name": "Dice (ET)", "values": [0.9, 0.8]}]})
    assert q.check_chart_block(ok) == []
    both = json.dumps({"type": "bar", "labels": ["A"], "series": [{"name": "Dice", "values": [0.9]}, {"name": "HD95", "values": [4.0]}]})
    assert q.check_chart_block(both)


def test_reference_verification_statuses_and_duplicates():
    catalog = {
        "a": {"title": "Paper A", "authors": "X, Y", "year": "2021", "venue": "arXiv:1", "doi": "", "url": "u"},
        "b": {"title": "Paper B", "authors": "X", "year": "2020", "doi": "", "url": ""},
        "c": {"title": "Paper C", "authors": "X", "year": "2020", "doi": "not-a-doi", "url": "u"},
        "d": {"title": "paper a!", "authors": "Z", "year": "2021", "venue": "v"},
    }
    res = {r["paper_id"]: r["status"] for r in verify_references(["a", "b", "c", "e"], catalog)["references"]}
    assert res == {"a": CATALOG_MATCHED, "b": PARTIALLY_VERIFIED, "c": INVALID, "e": UNVERIFIED}
    dup = {r["paper_id"]: r["status"] for r in verify_references(["a", "d"], catalog)["references"]}
    assert dup == {"a": CONFLICT, "d": CONFLICT}


TABLE = '```table\n{"caption": "Results [1]", "columns": ["Method", "Dice", "HD95"], "rows": [["nnU-Net [1]", "88.5", "4.2"], ["Other", "88.5", "–"], ["TabNet [2]", "77.7", "1.0"]]}\n```'


def test_numeric_claims_trace_to_source_pages():
    claims = extract_numeric_claims(TABLE)
    assert [c["value"] for c in claims] == ["88.5", "4.2", "88.5", "77.7", "1.0"]
    sources = {
        1: {"paper_id": "p1", "pdf_sha256": "h1", "chunks": [{"page": 8, "text": "nnU-Net reached Dice 88.5 and HD95 of 4.2 mm"}]},
        2: {"paper_id": "p2", "pdf_sha256": "h2", "chunks": [{"page": 3, "text": "no such value"}]},
    }
    out = {(r["location"]): r for r in trace_claims(claims, sources)}
    assert out["row 1, Dice"]["status"] == TRACED and out["row 1, Dice"]["pages"] == [8] and out["row 1, Dice"]["pdf_sha256"] == "h1"
    assert out["row 2, Dice"]["status"] == TRACED  # hàng không có [n] dùng [n] của caption
    assert out["row 3, Dice"]["status"] == UNTRACED
    assert trace_claims([{"block": "t", "location": "x", "value": "1.0", "cites": []}], sources)[0]["status"] == NO_CITATION


def _chunk(pid, text, page=1):
    return SimpleNamespace(chunk=SimpleNamespace(paper_id=pid, text=text, page=page))


def test_quality_gate_blocks_untraced_numbers_and_bad_references():
    cites = [SimpleNamespace(paper_id="p1"), SimpleNamespace(paper_id="p2")]
    state = {"citations": cites, "evidence": [_chunk("p1", "Dice 88.5 HD95 4.2", 8), _chunk("p2", "values 77.7", 2)]}
    catalog = {"p1": {"title": "T1", "authors": "A", "year": "2021", "url": "u"}, "p2": {"title": "T2", "authors": "B", "year": "2022", "url": "u"}}
    good = '```table\n{"caption": "R", "columns": ["M", "Dice"], "rows": [["A [1]", "88.5"], ["B [2]", "77.7"]]}\n```'
    report = run_quality_gate(state, good, catalog)
    assert report["passed"] and report["traceability"]["counts"][TRACED] == 2
    bad = '```table\n{"caption": "R", "columns": ["M", "Dice"], "rows": [["A [1]", "99.9"]]}\n```'
    failed = run_quality_gate(state, bad, catalog)
    assert not failed["passed"] and any("không tìm thấy" in b for b in failed["blocking"])
    broken = run_quality_gate(state, good, {**catalog, "p1": {"title": "T1", "authors": "A", "year": "2021", "doi": "bad"}})
    assert not broken["passed"] and any("INVALID" in b for b in broken["blocking"])


_RQ_DOC = (
    "## 1. Introduction\n### 1.3 Research Gaps and Research Questions\n"
    "**RQ1.** Which backbone architectures dominate glioma segmentation today?\n"
    "**RQ2.** How are the four modalities fused in published segmentation networks?\n\n"
    "## 2. Review Methodology\n### 2.1 Research Questions\n"
    "**RQ1.** Which backbone architectures dominate glioma segmentation today?\n"
    "**RQ2.** What are the open threats to validity in published segmentation studies?\n"
)
_GATE_STATE = {"citations": [SimpleNamespace(paper_id="p1")], "evidence": []}
_GATE_CATALOG = {"p1": {"title": "T1", "authors": "A", "year": "2021", "venue": "MICCAI"}}


def test_gate_blocks_rq_defined_differently_between_sections():
    report = run_quality_gate(_GATE_STATE, _RQ_DOC + "See [1].", _GATE_CATALOG)
    assert not report["passed"] and any("RQ2" in b for b in report["blocking"])
    assert report["research_questions"]["problems"]


def test_gate_blocks_claim_of_systematic_review_but_not_its_negation():
    bad = "We conducted a systematic review following PRISMA guidelines [1]."
    good = "This is a narrative review, not a systematic review, and no PRISMA flow was performed [1]."
    assert check_review_claims(bad)
    assert check_review_claims(good) == []
    failed = run_quality_gate(_GATE_STATE, bad, _GATE_CATALOG)
    assert not failed["passed"] and any("tổng quan" in b for b in failed["blocking"])
    assert run_quality_gate(_GATE_STATE, good, _GATE_CATALOG)["review_claims"]["problems"] == []


def test_merge_structure_issues_flips_passed_only_for_blocking():
    base = {"passed": True, "blocking": [], "warnings": ["w"]}
    assert merge_structure_issues(base, [], ["x"])["passed"] is True
    merged = merge_structure_issues(base, ["Table [7] treo"], [])
    assert merged["passed"] is False and merged["blocking"] == ["Table [7] treo"] and base["blocking"] == []
    assert merge_structure_issues(None, ["b"], []) is None


def test_figure_caption_checks():
    text = (
        "**Figure 2: Qualitative Visual Comparison**\n\n```image\n{\"ref\": \"F2\", \"caption\": \"Segmentation result of one case\"}\n```\n\n"
        "**Figure 3: Qualitative Visual Comparison**\n\n"
        "**Figure 4: Cascaded CNN output on a BraTS 2015 LGG case, green edema and red non-enhancing core [7]**\n"
    )
    warnings = check_figure_captions(text)
    assert sum("chung chung" in w for w in warnings) == 2
    assert any("trùng nhau" in w for w in warnings)
    assert any("giấy phép" in w for w in warnings)
    good = '**Figure 1: Cascaded CNN output on a BraTS 2015 LGG case, green edema, red core [7]**\n\n```image\n{"caption": "Cascaded CNN output on a BraTS 2015 LGG case [7], reproduced from that paper"}\n```'
    assert check_figure_captions(good) == []


def test_reference_publication_classification_and_gate_warnings():
    assert classify_publication({"venue": "arXiv preprint arXiv:1709.00382"}) == "preprint"
    assert classify_publication({"venue": "MICCAI 2020"}) == "published"
    assert classify_publication({"url": "https://arxiv.org/abs/1"}) == "preprint"
    assert classify_publication({"doi": "10.1016/j.media.2016.05.004"}) == "published"
    assert classify_publication(None) == "unknown"
    catalog = {"p1": {"title": "T1", "authors": "A", "year": "2021", "venue": "arXiv preprint"}, "p2": {"title": "T2", "authors": "B", "year": "2022"}}
    state = {"citations": [SimpleNamespace(paper_id="p1"), SimpleNamespace(paper_id="p2")], "evidence": []}
    report = run_quality_gate(state, "A [1] and B [2].", catalog)
    assert report["references"]["publication"]["preprint"] == 1
    assert any("preprint" in w for w in report["warnings"]) and any("thiếu metadata" in w for w in report["warnings"])


def test_gate_warns_without_prior_survey_and_reports_science_qa():
    text = "No source reports per-modality degradation [1]. T1ce and T1c differ."
    report = run_quality_gate(_GATE_STATE, text, _GATE_CATALOG)
    assert any(w.startswith("novelty:") for w in report["warnings"])
    assert any("thuật ngữ" in w for w in report["science_qa"]) and "study_profile" in report
    with_survey = {"p1": {**_GATE_CATALOG["p1"], "title": "A survey of glioma segmentation"}}
    assert not any(w.startswith("novelty:") for w in run_quality_gate(_GATE_STATE, text, with_survey)["warnings"])


def test_prior_surveys_fact_lists_only_real_catalog_surveys():
    from app.agent.nodes.synthesize_node import _prior_surveys_fact

    state = {"citations": [SimpleNamespace(paper_id="s1")]}
    catalog = {"s1": {"title": "A Review of MRI Fusion", "year": "2022"}, "s2": {"title": "Deep Survey of X", "year": "2020"}, "p3": {"title": "UNet"}}
    fact = _prior_surveys_fact(state, catalog)
    assert "[1] A Review of MRI Fusion (2022)" in fact and "(not retrieved, cannot be cited) Deep Survey of X" in fact and "UNet" not in fact
    assert "none" in _prior_surveys_fact(state, {"p3": {"title": "UNet"}})
