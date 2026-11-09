"""Unit tests for citation cleaner and dataset catalog."""

from app.agent.evidence.citation_cleaner import (
    clean_and_deduplicate_citations,
    clean_and_deduplicate_citations_ex,
    collapse_duplicate_citations,
)
from app.agent.evidence.dataset_catalog import KNOWN_DATASETS, get_dataset_grounding_context
from app.core.schemas import Citation


def test_dataset_catalog():
    assert "llmbar" in KNOWN_DATASETS
    assert KNOWN_DATASETS["llmbar"]["total_pairs"] == 419
    context = get_dataset_grounding_context()
    assert "LLMBar" in context
    assert "MT-Bench" in context
    assert "Chatbot Arena" in context


def test_clean_and_deduplicate_citations():
    citations = [
        Citation(
            paper_id="Title: The Comparative Trap Authors: Hawon Jeong et al. (2024)",
            chunk_id="c1",
            text_snippet="Snippet 1",
        ),
        Citation(
            paper_id="Title: Judging the Judges Authors: Lin Shi et al. (2024)",
            chunk_id="c2",
            text_snippet="Snippet 2",
        ),
        Citation(
            paper_id="Title: The Comparative Trap Authors: Hawon Jeong et al. (2024)",
            chunk_id="c3",
            text_snippet="Snippet 3 (duplicate paper)",
        ),
    ]

    text = "We compare with [1] and [3] on position bias, along with [2]."
    updated_text, clean_refs = clean_and_deduplicate_citations(citations, text)

    # [1] and [3] both map to the same paper, which becomes [1]. [2] becomes [2].
    assert "[1]" in updated_text
    assert "[2]" in updated_text
    assert "[3]" not in updated_text
    assert len(clean_refs) == 2
    assert "Hawon Jeong et al." in clean_refs[0]
    assert "Page: 1" not in clean_refs[0]
    assert "Snippet" not in clean_refs[0]


def test_collapse_duplicate_citations_in_text():
    assert collapse_duplicate_citations("as shown in [1], [1] and [2][2], [3], [1].") == "as shown in [1] and [2], [3], [1]."
    assert collapse_duplicate_citations("only [1] and [2].") == "only [1] and [2]."
    assert collapse_duplicate_citations("| Evaluation | 2012–2021 | [1]–[1] |") == "| Evaluation | 2012–2021 | [1] |"
    assert collapse_duplicate_citations("see [1]–[14] and [3]-[3]") == "see [1]–[14] and [3]"


def test_collapse_keeps_code_blocks_but_fixes_table_cells():
    text = '```chart\n{"values": [[1], [1]]}\n```\n\n```table\n{"rows": [["HeMIS [7], [7]", "0.8"]]}\n```'
    out = collapse_duplicate_citations(text)
    assert '[[1], [1]]' in out
    assert "HeMIS [7]\"" in out and "[7], [7]" not in out


def test_remap_merging_two_chunks_of_one_paper_yields_single_marker():
    citations = [
        Citation(paper_id="Title: Alpha Net Authors: A One et al. (2020)", chunk_id="c1", text_snippet="s1"),
        Citation(paper_id="Title: Alpha Net Authors: A One et al. (2020)", chunk_id="c2", text_snippet="s2"),
    ]
    updated, _ = clean_and_deduplicate_citations(citations, "Dice improves [1], [2] on BraTS.")
    assert "[1], [1]" not in updated and "[1]" in updated


def test_cluster_markers_are_remapped_not_left_dangling():
    """'[1, 3]' trong một cặp ngoặc vẫn được đánh số lại theo paper (trước đây số trong cụm bị bỏ qua -> '[73]' treo)."""
    citations = [
        Citation(paper_id="Title: Alpha Net Authors: A One et al. (2020)", chunk_id="c1", text_snippet="s1"),
        Citation(paper_id="Title: Beta Net Authors: B Two et al. (2021)", chunk_id="c2", text_snippet="s2"),
        Citation(paper_id="Title: Alpha Net Authors: A One et al. (2020)", chunk_id="c3", text_snippet="s3"),
    ]
    updated, refs = clean_and_deduplicate_citations(citations, "Fusion [2, 3] and ranges [1–2].")
    assert len(refs) == 2
    assert "[3]" not in updated and "2, 3" not in updated
    assert "Fusion [1], [2]" in updated or "Fusion [2], [1]" in updated


def test_numbered_citations_follow_the_new_numbering():
    """`numbered[k-1]` phải là citation của reference [k] SAU khi đánh số lại (gộp trùng, bỏ paper không cite)."""
    citations = [
        Citation(paper_id="Title: Alpha Authors: A One (2024)", chunk_id="c1", text_snippet="a"),
        Citation(paper_id="Title: Beta Authors: B Two (2023)", chunk_id="c2", text_snippet="b"),
        Citation(paper_id="Title: Alpha Authors: A One (2024)", chunk_id="c3", text_snippet="a2"),
        Citation(paper_id="Title: Gamma Authors: C Three (2022)", chunk_id="c4", text_snippet="g"),
    ]
    text = "Gamma is cited first [4], then Alpha [3] and again [1]."

    updated, refs, numbered = clean_and_deduplicate_citations_ex(citations, text)

    assert len(refs) == len(numbered) == 2  # Beta không được cite → bị bỏ
    # Alpha (canon 1) đứng trước Gamma (canon 3) theo thứ tự trong danh sách gốc
    assert "Alpha" in numbered[0].paper_id and "Gamma" in numbered[1].paper_id
    assert updated == "Gamma is cited first [2], then Alpha [1] and again [1]."
