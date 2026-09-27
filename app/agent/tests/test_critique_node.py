from unittest.mock import MagicMock

from app.agent.nodes.critique_node import critique_node
from app.core.schemas import Chunk, Citation, ScoredChunk


def _state(draft: str, citations: list[Citation]) -> dict:
    return {
        "draft": draft,
        "citations": citations,
        "evidence": [ScoredChunk(chunk=Chunk(id="a", paper_id="p1", text="evidence", chunk_index=0), score=0.9)],
        "iterations": 0,
    }


def test_skips_hallucination_llm_call_when_citation_invalid():
    """Citation sai -> chắc chắn phải viết lại vòng sau, không cần tốn thêm 1 lời gọi LLM."""
    fake_llm = MagicMock()
    state = _state(draft="Nội dung có trích dẫn sai [9].", citations=[])

    result = critique_node(state, llm=fake_llm)

    fake_llm.generate.assert_not_called()
    assert "trích dẫn không hợp lệ" in result["critique_feedback"].lower()


def test_calls_hallucination_check_when_citations_are_valid():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(text='{"unsupported_sentences": []}')
    citations = [Citation(paper_id="p1", chunk_id="a", text_snippet="...")]
    state = _state(draft="Nội dung hợp lệ [1].", citations=citations)

    result = critique_node(state, llm=fake_llm)

    fake_llm.generate.assert_called_once()
    assert result["critique_feedback"] is None
