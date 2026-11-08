from app.agent.evidence.report_structure import (
    check_cross_references,
    finalize_structure,
    finalize_structure_report,
    renumber_captions,
    renumber_captions_report,
    renumber_sections,
    source_diversity_warning,
    strip_dangling_citations,
)


def test_renumber_sections_fixes_misplaced_subsection():
    text = "## 1. Intro\n### 1.1 A\n## 2. Tax\n### 2.1 B\n### 1.4 Paper Organization\n## 3. M\n### 3.1 C"
    out = renumber_sections(text)
    assert "### 2.2 Paper Organization" in out
    assert "## 3. M" in out and "### 3.1 C" in out


def test_renumber_sections_skips_code_fences_and_unnumbered():
    text = "## Abstract\n## 1. Intro\n```mermaid\n## 9. not heading\n```\n## References"
    assert renumber_sections(text) == text


def test_renumber_captions_dedupes_and_remaps_unique_refs():
    text = "**Table 1: A**\n\n**Table 2: B**\n\nSee Table 2.\n\n**Figure 1: X**\n\n**Figure 1: Y**\n\nSee Figure 1."
    out = renumber_captions(text)
    assert "**Figure 2: Y**" in out
    assert "See Figure 2." in out  # mơ hồ → gán theo caption gần nhất (không còn giữ số cũ)
    assert "See Table 2." in out


def test_renumber_captions_updates_reference_after_shift():
    text = "**Table 1: A**\n\n**Table 1: B**\n\n**Table 3: C**\n\nSee Table 3."
    out = renumber_captions(text)
    assert "**Table 3: C**" in out
    text2 = "**Table 2: A**\n\nSee Table 2."
    assert renumber_captions(text2) == "**Table 1: A**\n\nSee Table 1."


def test_strip_dangling_citations():
    out, removed = strip_dangling_citations("Claim [1] and more [4], done [2].", 2)
    assert out == "Claim [1] and more, done [2]."
    assert removed == [4]
    out, removed = strip_dangling_citations("A [1].", 0)
    assert out == "A." and removed == [1]


def test_source_diversity_warning():
    assert source_diversity_warning("x [1]", 0)
    assert source_diversity_warning(" ".join(["a [1]"] * 12), 1)
    assert source_diversity_warning(" ".join(f"a [{i % 4 + 1}]" for i in range(12)), 4) is None


def test_finalize_structure_runs_both():
    out = finalize_structure("## 1. A\n### 1.1 x\n**Table 5: T**\n")
    assert "**Table 1: T**" in out


def test_drop_ungrounded_claims_removes_unsupported_number_sentence():
    from app.agent.report_postprocess import drop_ungrounded_claims

    text = "Accuracy reached 91.2% on MVTec [1]. Costs fell by 2.5x [1]. Plain claim [1]."
    out, dropped = drop_ungrounded_claims(text, "Result: 91.2 accuracy")
    assert "91.2%" in out
    assert "2.5x" not in out and len(dropped) == 1
    assert "Plain claim [1]." in out


def test_synthesize_blocks_when_no_citations():
    import pytest

    from app.agent.nodes.synthesize_node import InsufficientEvidenceError, synthesize_node

    with pytest.raises(InsufficientEvidenceError):
        synthesize_node({"question": "q", "citations": []})


def test_ambiguous_ref_resolved_by_sentence_overlap():
    text = (
        "**Table 4: Fusion strategies by combination stage**\n\n"
        "**Table 4: Quantitative comparison of published Dice results**\n\n"
        "The quantitative comparison of Dice results in Table 4 is not comparable across datasets.\n\n"
        "Fusion strategies by combination stage are listed in Table 4."
    )
    out, low = renumber_captions_report(text)
    assert "**Table 1: Fusion strategies" in out and "**Table 2: Quantitative comparison" in out
    assert "Dice results in Table 2 is not" in out
    assert "combination stage are listed in Table 1." in out
    assert low == []


def test_ambiguous_ref_without_overlap_is_reported_low_confidence():
    text = "**Figure 1: Alpha pipeline**\n\n**Figure 1: Omega curves**\n\nSee Figure 1 above."
    _, low = renumber_captions_report(text)
    assert low and "Figure 1" in low[0]


def test_cross_references_dangling_is_reported():
    text = "**Table 1: A**\n\n**Table 2: B**\n\nResults in Table 5 and Table 2.\n\nSee Figure 3."
    problems = check_cross_references(text)
    assert any("Table [5]" in p for p in problems)
    assert any("Figure [3]" in p for p in problems)


def test_cross_references_ignores_source_paper_tables_and_fences():
    text = "**Table 1: A**\n\nAs in Table 9 of [7] and Table 2 in the original paper.\n\n```table\n{\"caption\": \"see Table 8\"}\n```"
    assert check_cross_references(text) == []


def test_finalize_structure_report_returns_all_three():
    fixed, dangling, low = finalize_structure_report("**Table 3: A**\n\nSee Table 3 and Table 6.")
    assert "**Table 1: A**" in fixed and "Table 1 and Table 6" in fixed
    assert dangling and not low
