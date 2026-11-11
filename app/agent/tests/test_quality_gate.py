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


def test_prior_surveys_fact_keeps_only_same_topic_surveys():
    from app.agent.nodes.synthesize_node import _prior_surveys_fact

    state = {"citations": [], "question": "Multimodal MRI brain tumor segmentation on BraTS"}
    catalog = {
        "s1": {"title": "Deep learning for brain tumor segmentation: a survey", "year": "2021"},
        "s2": {"title": "A survey on deepfake detection", "year": "2022"},
        "s3": {"title": "Medical image segmentation review", "year": "2020"},
    }
    fact = _prior_surveys_fact(state, catalog)
    assert "brain tumor segmentation" in fact and "deepfake" not in fact and "Medical image segmentation" not in fact
    assert "2 other survey(s)" in fact
    assert "none on this topic" in _prior_surveys_fact(state, {"s2": catalog["s2"]})


def test_paper_count_above_corpus_is_flagged():
    from app.agent.evidence.consistency_check import check_paper_counts

    text = "We analyze 73 studies.\n\nThe repository has 40 papers; 34 distinct papers were retrieved.\n\n## References\n[1] 99 papers"
    assert check_paper_counts(text, 40) == ["bài nói 73 paper/nghiên cứu nhưng kho chỉ có 40 paper"]
    assert check_paper_counts("We analyze 40 papers.", 40) == []


def test_gate_on_renumbered_text_traces_through_numbered_citations():
    """Bản cuối đã đánh số lại: [1] mới là paper p2 (p1 không được cite) → truy vết phải đi theo `numbered_citations`."""
    all_cites = [SimpleNamespace(paper_id="p1"), SimpleNamespace(paper_id="p2")]
    state = {"citations": all_cites, "evidence": [_chunk("p1", "Dice 11.1", 1), _chunk("p2", "Dice 88.5", 8)]}
    catalog = {"p1": {"title": "T1", "authors": "A", "year": "2021", "url": "u"}, "p2": {"title": "T2", "authors": "B", "year": "2022", "url": "u"}}
    text = '```table\n{"caption": "R", "columns": ["M", "Dice"], "rows": [["B [1]", "88.5"]]}\n```'

    raw_view = run_quality_gate(state, text, catalog)  # đọc [1] theo chỉ số gốc = p1 → 88.5 không có trong p1
    final_view = run_quality_gate(state, text, catalog, numbered_citations=[all_cites[1]])

    assert raw_view["traceability"]["counts"][UNTRACED] == 1
    assert final_view["traceability"]["counts"][TRACED] == 1
    # độ phủ kho tính trên kho đầy đủ: p1 không còn reference nào trong bản cuối → "1/2 paper chưa được cite"
    assert any("độ phủ kho: 1/2" in w for w in final_view["blocking"])


def test_final_gate_flags_method_name_attributed_to_wrong_paper():
    cites = [SimpleNamespace(paper_id="p1", text_snippet="nnU-Net Revisited benchmarks U-Net on BraTS")]
    state = {"citations": cites, "evidence": [], "results": []}
    catalog = {"p1": {"title": "nnU-Net Revisited", "authors": "Isensee", "year": "2024", "url": "u"}}
    bad = run_quality_gate(state, "Swin UNETR [1] improves over the baseline.", catalog, numbered_citations=cites)
    assert any("gán sai nguồn" in w and "UNETR" in w for w in bad["warnings"])
    good = run_quality_gate(state, "nnU-Net [1] is a strong baseline.", catalog, numbered_citations=cites)
    assert not any("gán sai nguồn" in w for w in good["warnings"])


def test_gate_blocks_when_small_corpus_not_fully_cited():
    """Kho nhỏ (≤ giới hạn phủ trọn) phải cite hết: paper bị bỏ sót là lỗi chặn, không chỉ cảnh báo."""
    state = {"citations": [SimpleNamespace(paper_id="p1"), SimpleNamespace(paper_id="p2")], "evidence": []}
    catalog = {pid: {"title": pid, "authors": "A", "year": "2021", "url": "u"} for pid in ("p1", "p2")}
    partial = run_quality_gate(state, "Only one source [1].", catalog)
    assert not partial["passed"] and any(b.startswith("độ phủ kho: 1/2") for b in partial["blocking"])
    full = run_quality_gate(state, "Both sources [1][2].", catalog)
    assert not any(b.startswith("độ phủ kho") for b in full["blocking"])


def test_axis_count_must_agree_across_sections():
    from app.agent.evidence.consistency_check import check_axis_count

    bad = "## Abstract\nA five-axis taxonomy.\n\n## 3. Taxonomy\nWe organize methods along four non-orthogonal axes."
    assert check_axis_count(bad) and "4 trục" in check_axis_count(bad)[0] and "5 trục" in check_axis_count(bad)[0]
    assert not check_axis_count("## Abstract\nFour axes.\n\n## 3.\nWe use four method-design axes and Axis A to D.")


def test_ledger_claim_contradiction_only_when_no_missing_modality_groups():
    from app.agent.evidence.consistency_check import check_ledger_claims

    claim = "We report 262 verified records, each with a missing-modality configuration."
    assert check_ledger_claims(claim, missing_groups=0)
    assert not check_ledger_claims(claim, missing_groups=3)  # sổ cái thật có nhóm missing-modality
    assert not check_ledger_claims("No missing-modality result was extracted into the records.", missing_groups=0)


def test_novelty_first_claim_is_blocking_only_for_self_claims():
    from app.agent.evidence.consistency_check import check_novelty_claims

    out = check_novelty_claims("This is the first comprehensive mapping of fusion.", n_prior_surveys=1)
    assert out and "kho chỉ có 1 survey" in out[0]
    assert check_novelty_claims("We propose the first unified framework for glioma triage.")
    assert not check_novelty_claims("Prior work is not the first comprehensive survey.")
    assert not check_novelty_claims("Menze et al. introduced the first BraTS benchmark [3].")
    report = run_quality_gate(_GATE_STATE, "To the best of our knowledge, this is the first survey of fusion [1].", _GATE_CATALOG)
    assert any("tuyên bố tính mới" in b for b in report["blocking"])


def test_soften_novelty_claims_removes_first_but_keeps_other_sources():
    from app.agent.evidence.repair import soften_novelty_claims

    text = (
        "## 1. Introduction\nTo the best of our knowledge, this is the first comprehensive survey of fusion [1]. "
        "We are the first to propose a unified taxonomy. Menze et al. built the first BraTS benchmark [2].\n"
        '```chart\n{"caption": "this is the first survey"}\n```\n## References\n[1] The first survey of X.\n'
    )
    out, changed = soften_novelty_claims(text)
    assert "This is a comprehensive survey of fusion [1]." in out
    assert "We propose a unified taxonomy." in out
    assert "built the first BraTS benchmark [2]" in out and '"this is the first survey"' in out and "[1] The first survey of X." in out
    assert len(changed) == 2


def test_limitation_denial_only_when_ledger_has_missing_modality_groups():
    from app.agent.evidence.consistency_check import check_limitation_denial

    text = "No missing-modality result was extracted into structured records."
    assert check_limitation_denial(text, missing_groups=3)
    assert not check_limitation_denial(text, missing_groups=0)  # đúng sự thật khi sổ cái không có


def test_prior_survey_claim_must_point_to_survey_titles():
    from app.agent.evidence.consistency_check import check_prior_survey_claims

    titles = {3: "Identifying the Best Machine Learning Algorithms for Brain Tumor Segmentation", 6: "The BraTS Challenge 2023: BraSyn", 8: "Diffusion Models for Medical Image Analysis: A Comprehensive Survey"}
    out = check_prior_survey_claims("Prior surveys [3], [6], [8] predate transformers.", titles)
    assert [o[:3] for o in out] == ["[3]", "[6]"]
    assert not check_prior_survey_claims("Prior surveys [8] cover diffusion.", titles)
    assert not check_prior_survey_claims("Methods are described in [3].", titles)  # không nhắc 'prior survey'


def test_overgeneralization_needs_scope():
    from app.agent.evidence.consistency_check import check_overgeneralization

    bad = "mmFormer outperforms HeMIS on all 15 subsets, so attention-based fusion is the most effective paradigm in the field overall."
    assert check_overgeneralization(bad)
    ok = "Within the protocol of [23], mmFormer outperforms HeMIS on all 15 subsets; this does not generalise to the field."
    assert not check_overgeneralization(ok)


def test_reference_years_flags_two_years_but_ignores_arxiv_ids():
    from app.agent.evidence.consistency_check import check_reference_years

    text = "Body.\n## References\n[37] A, \"T,\" *Venue*, 2024. Preprint 2022.\n[38] B, \"U,\" arXiv:2007.09479, 2020.\n"
    out = check_reference_years(text)
    assert len(out) == 1 and out[0].startswith("[37]")


def test_chart_point_uses_its_own_label_citation_not_caption():
    chart = '```chart\n{"type": "dot", "caption": "Dice [1], [2]", "labels": ["A [1]", "B [2]"], "series": [{"name": "ET", "values": [88.5, 77.7]}]}\n```'
    assert [c["cites"] for c in extract_numeric_claims(chart)] == [[1], [2]]
    scatter = '```chart\n{"type": "bar", "caption": "Dice [1], [2]", "series": [{"name": "B [2]", "values": [77.7]}]}\n```'
    assert extract_numeric_claims(scatter)[0]["cites"] == [2]


def _ledger(*pairs):
    from dataclasses import asdict

    return [asdict(replace(BASE, paper_id=pid, value=v)) | {"modality": list(BASE.modality)} for pid, v in pairs]


def test_gate_blocks_value_cited_to_paper_that_does_not_own_the_record():
    cites = [SimpleNamespace(paper_id="p1"), SimpleNamespace(paper_id="p2"), SimpleNamespace(paper_id="p3")]
    # p2 tình cờ có chuỗi "88.5" trong văn bản nhưng sổ cái ghi 88.5 là của p1 → cite [2] là nhầm nguồn
    evidence = [_chunk("p1", "Dice 88.5", 8), _chunk("p2", "Dice 77.7, epoch 88.5", 2), _chunk("p3", "Dice 88.5", 4)]
    catalog = {f"p{i}": {"title": f"T{i}", "authors": "A", "year": "2021", "url": "u"} for i in (1, 2, 3)}
    state = {"citations": cites, "evidence": evidence, "results": _ledger(("p1", 88.5), ("p2", 77.7))}
    wrong = '```chart\n{"type": "dot", "caption": "Dice", "labels": ["A [2]"], "series": [{"name": "ET", "values": [88.5]}]}\n```'
    report = run_quality_gate(state, wrong, catalog)
    assert not report["passed"] and any("trích dẫn sai nguồn số liệu" in b and "p1" in b for b in report["blocking"])
    right = wrong.replace("A [2]", "A [1]")
    assert not any("sai nguồn" in b for b in run_quality_gate(state, right, catalog)["blocking"])
    # p3 chưa có record trong sổ cái → không đủ căn cứ, không chặn
    unknown = wrong.replace("A [2]", "A [3]")
    assert not any("sai nguồn" in b for b in run_quality_gate(state, unknown, catalog)["blocking"])


def test_misattributed_chart_point_is_redacted_by_repair():
    from app.agent.evidence.quality_gate import trace_text_records
    from app.agent.evidence.repair import redact_untraced_chart_points

    cites = [SimpleNamespace(paper_id="p1"), SimpleNamespace(paper_id="p2")]
    state = {"citations": cites, "evidence": [_chunk("p1", "Dice 88.5"), _chunk("p2", "Dice 77.7, epoch 88.5")],
             "results": _ledger(("p1", 88.5), ("p2", 77.7))}
    text = '```chart\n{"type": "dot", "caption": "Dice", "labels": ["A [2]", "B [2]"], "series": [{"name": "ET", "values": [88.5, 77.7]}]}\n```'
    records = trace_text_records(state, text)
    assert [r["status"] for r in records] == [UNTRACED, TRACED] and records[0]["misattributed_to"] == ["p1"]
    fixed, removed = redact_untraced_chart_points(text, records)
    assert [r["value"] for r in removed] == ["88.5"] and "null" in fixed


def test_methodology_disclosure_inserts_only_missing_facts():
    from app.agent.evidence.repair import ensure_methodology_disclosure

    text = (
        "## 1. Introduction\nIntro.\n## 2. Review Methodology\nThis narrative review covers the corpus.\n"
        "### 2.1 Review Scope\nScope.\n## 3. Taxonomy\nNo screening here either.\n"
    )
    out, added = ensure_methodology_disclosure(text, 24, 117, 15)
    assert added == ["papers", "records", "screening", "rob_grade"]  # 'narrative' đã có; 'screening' ở mục 3 không tính
    sec2 = out.split("## 2. Review Methodology")[1].split("## 3.")[0]
    assert sec2.index("**Review type and limitations.**") < sec2.index("### 2.1")
    assert "synthesizes 24 cited papers" in sec2 and "117 quantitative result records were extracted from 15" in sec2
    assert "GRADE" in sec2 and "This article is a narrative review" not in sec2
    again, added2 = ensure_methodology_disclosure(out, 24, 117, 15)
    assert added2 == [] and again == out  # chạy lại không chèn lần nữa


def test_methodology_disclosure_without_section_or_records():
    from app.agent.evidence.repair import ensure_methodology_disclosure

    assert ensure_methodology_disclosure("## 1. Introduction\nx\n", 3, 0, 0) == ("## 1. Introduction\nx\n", [])
    out, _ = ensure_methodology_disclosure("## 2. Methodology\nWe review papers.\n", 3, 0, 0)
    assert "No quantitative result record could be extracted" in out and out.endswith("\n\n")
