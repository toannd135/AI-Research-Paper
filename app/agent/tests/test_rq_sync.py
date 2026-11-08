from app.agent.evidence.rq_sync import (
    canonical_rqs,
    check_rq_definitions,
    enforce_rqs,
    rq_block,
    section_rqs,
)

BLUEPRINT = """7. RESEARCH QUESTIONS
RQ1. Which backbone architectures dominate brain tumor segmentation?
RQ2. At which stage are the four MRI modalities fused?
RQ3. How is robustness to missing modalities achieved?
"""

REPORT = """## 1. Introduction
### 1.3 Research Gaps and Research Questions
Gaps first.

**RQ1.** What are the dominant architecture backbones for segmentation of glioma?
**RQ2.** What do threats to validity look like across published studies today?
**RQ3.** Which quantitative results can be compared across the cited benchmark papers?

## 2. Review Methodology
### 2.1 Research Questions
**RQ1.** What are the dominant architecture backbones for segmentation of glioma?
**RQ2.** At which stage is information from the four modalities fused in published work?
**RQ3.** Which missing-modality robustness paradigms exist in the cited literature?

## 7. Conclusion
We answer RQ1, RQ2 and RQ3.
"""


def test_canonical_rqs_reads_ordered_questions():
    assert canonical_rqs(BLUEPRINT) == [
        "Which backbone architectures dominate brain tumor segmentation?",
        "At which stage are the four MRI modalities fused?",
        "How is robustness to missing modalities achieved?",
    ]


def test_canonical_rqs_rejects_gaps_and_too_few():
    assert canonical_rqs("RQ1. Only one question that is long enough here") == []
    assert canonical_rqs("RQ1. First long enough question text\nRQ3. Third long enough question text") == []


def test_mentions_are_not_definitions():
    assert section_rqs("## 7. Conclusion\nWe answer RQ1 and RQ2.\n") == {}


def test_mismatch_between_sections_is_reported():
    problems = check_rq_definitions(REPORT)
    assert any("RQ2" in p for p in problems)
    assert any("RQ3" in p for p in problems)
    assert not any("RQ1" in p for p in problems)


def test_enforce_makes_sections_identical_and_gate_clean():
    canon = canonical_rqs(BLUEPRINT)
    fixed = enforce_rqs(REPORT, canon)
    assert check_rq_definitions(fixed) == []
    rqs = section_rqs(fixed)
    assert all([b for _, b in v] == canon for v in rqs.values())
    assert fixed.count("**RQ1.**") == 2  # giữ định dạng in đậm
    assert "We answer RQ1, RQ2 and RQ3." in fixed  # không đụng tới phần khác


def test_enforce_skips_section_when_count_differs():
    text = REPORT.replace("**RQ3.** Which quantitative results can be compared across the cited benchmark papers?\n", "", 1)
    canon = canonical_rqs(BLUEPRINT)
    fixed = enforce_rqs(text, canon)
    intro_before = section_rqs(text)["1.3 research gaps and research questions"]
    assert section_rqs(fixed)["1.3 research gaps and research questions"] == intro_before
    # mục 2.1 có đủ 3 dòng nên vẫn được ép
    assert [b for _, b in section_rqs(fixed)["2.1 research questions"]] == canon


def test_different_number_sets_reported():
    text = REPORT.replace("**RQ3.** Which missing-modality robustness paradigms exist in the cited literature?\n", "")
    assert any("không nhất quán" in p for p in check_rq_definitions(text))


def test_rq_block_lists_all_and_forbids_changes():
    block = rq_block(canonical_rqs(BLUEPRINT))
    assert "RQ3. How is robustness" in block and "Never add, drop, reorder" in block
    assert rq_block([]) == ""
