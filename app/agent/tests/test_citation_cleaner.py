"""Unit tests for citation cleaner and dataset catalog."""

from app.agent.evidence.citation_cleaner import clean_and_deduplicate_citations, collapse_duplicate_citations
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
