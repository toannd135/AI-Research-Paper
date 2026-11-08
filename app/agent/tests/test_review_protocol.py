"""Giao thức review do người dùng khai báo: kiểm tra số học, REVIEW FACTS nguyên văn, sơ đồ PRISMA tất định."""

import copy
import json

from app.agent.evidence.consistency_check import check_review_claims
from app.agent.evidence.review_protocol import (
    inject_prisma,
    load_protocol,
    prisma_block,
    protocol_facts,
    validate_protocol,
)

PROTOCOL = {
    "review_type": "systematic",
    "guideline": "PRISMA 2020",
    "databases": [
        {"name": "PubMed", "search_string": "(glioma) AND (missing modality)", "date": "2026-10-01", "hits": 120},
        {"name": "Scopus", "search_string": "TITLE-ABS-KEY(glioma AND \"missing modality\")", "date": "2026-10-01", "hits": 80},
    ],
    "inclusion_criteria": ["BraTS evaluation", "peer-reviewed"],
    "exclusion_criteria": ["no quantitative results"],
    "counts": {"identified": 200, "duplicates_removed": 50, "screened": 150, "excluded_screening": 100,
               "full_text_assessed": 50, "excluded_full_text": {"no BraTS": 10, "no missing-modality results": 5}, "included": 35},
    "reviewers": {"screening": 2, "extraction": 1, "disagreement_resolution": "discussion with a third author"},
    "quality_assessment": "adapted CLAIM checklist",
}


def test_valid_protocol_passes_and_counts_must_add_up():
    assert validate_protocol(PROTOCOL, corpus_size=35) == []
    bad = copy.deepcopy(PROTOCOL)
    bad["counts"]["included"] = 40
    problems = validate_protocol(bad, corpus_size=35)
    assert any("≠ included=40" in p for p in problems) and any("kho PDF có 35" in p for p in problems)


def test_protocol_requires_dates_reviewers_and_matching_guideline():
    bad = copy.deepcopy(PROTOCOL)
    bad["databases"][0]["date"] = ""
    bad["guideline"] = "PRISMA-ScR"
    del bad["reviewers"]["disagreement_resolution"]
    problems = " | ".join(validate_protocol(bad))
    assert "ngày tìm kiếm" in problems and "guideline" in problems and "disagreement_resolution" in problems
    assert validate_protocol({"review_type": "meta"}) and validate_protocol({"review_type": "narrative"}) == []


def test_facts_and_prisma_use_declared_numbers_only():
    facts = protocol_facts(PROTOCOL)
    assert "PubMed searched on 2026-10-01" in facts and "35 included" in facts and "2 for screening" in facts
    block = prisma_block(PROTOCOL)
    assert "n = 200" in block and "n = 35" in block and "no BraTS: 10" in block
    report = "## 2. Review Methodology\n### 2.2 Corpus\ntext\n### 2.3 Data Extraction\n"
    out = inject_prisma(report, block)
    assert out.index("```mermaid") < out.index("### 2.3") and inject_prisma(out, block) == out


def test_review_claims_follow_declared_type():
    claim = "This systematic review follows PRISMA 2020."
    assert check_review_claims(claim) and check_review_claims(claim, "systematic") == []
    assert check_review_claims("We follow PRISMA-ScR.", "scoping") == []
    assert check_review_claims("This systematic review follows PRISMA-ScR.", "scoping")


def test_load_protocol_from_upload_dir(tmp_path):
    assert load_protocol(str(tmp_path)) is None
    (tmp_path / "review_protocol.json").write_text(json.dumps(PROTOCOL), encoding="utf-8")
    assert load_protocol(str(tmp_path))["review_type"] == "systematic"
    (tmp_path / "review_protocol.json").write_text("{broken", encoding="utf-8")
    assert load_protocol(str(tmp_path)) is None
