"""Unit tests for citation cleaner and dataset catalog."""

from app.agent.evidence.citation_cleaner import clean_and_deduplicate_citations
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
