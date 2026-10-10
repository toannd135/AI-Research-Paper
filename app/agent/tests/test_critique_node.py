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


def test_rejects_draft_with_placeholders():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(text='{"unsupported_sentences": []}')
    citations = [Citation(paper_id="p1", chunk_id="a", text_snippet="...")]
    state = _state(draft="Nội dung cần bổ sung [CẦN THÊM NGUỒN] [1].", citations=citations)

    result = critique_node(state, llm=fake_llm)

    assert result["critique_feedback"] is not None
    assert "[CẦN THÊM NGUỒN]" in result["critique_feedback"]


def test_rejects_citation_misattribution():
    fake_llm = MagicMock()
    citations = [Citation(paper_id="HippoRAG Memory", chunk_id="a", text_snippet="hipporag")]
    state = _state(draft="Phương pháp IRCoT [1] thực hiện multi-hop.", citations=citations)

    result = critique_node(state, llm=fake_llm)

    assert result["critique_feedback"] is not None
    assert "gán sai nguồn" in result["critique_feedback"].lower()


def test_rejects_hype_language():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(text='{"unsupported_sentences": []}')
    citations = [Citation(paper_id="Paper 1", chunk_id="a", text_snippet="paper 1")]
    state = _state(draft="This is the first framework that provides mechanistic guarantee [1].", citations=citations)

    result = critique_node(state, llm=fake_llm)

    assert result["critique_feedback"] is not None
    assert "khẳng định tuyệt đối" in result["critique_feedback"].lower()


def test_rejects_encoder_generative_conflict():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(text='{"unsupported_sentences": []}')
    citations = [Citation(paper_id="Paper 1", chunk_id="a", text_snippet="paper 1")]
    state = _state(draft="We use DeBERTa to generate the rewritten answer [1].", citations=citations)

    result = critique_node(state, llm=fake_llm)

    assert result["critique_feedback"] is not None
    assert "deberta là mô hình encoder-only" in result["critique_feedback"].lower()


def test_rejects_pipeline_leakage():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(text='{"unsupported_sentences": []}')
    citations = [Citation(paper_id="Paper 1", chunk_id="a", text_snippet="paper 1")]
    state = _state(draft="As detailed in Blueprint §3.5 and Global Notation Lock [1].", citations=citations)

    result = critique_node(state, llm=fake_llm)

    assert result["critique_feedback"] is not None
    assert "rò rỉ siêu dữ liệu pipeline" in result["critique_feedback"].lower()


def test_rejects_budget_arithmetic_conflict():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(text='{"unsupported_sentences": []}')
    citations = [Citation(paper_id="Paper 1", chunk_id="a", text_snippet="paper 1")]
    state = _state(draft="The total cost was $2.70 in Table 4, but Section 5 reported $0.90 [1].", citations=citations)

    result = critique_node(state, llm=fake_llm)

    assert result["critique_feedback"] is not None
    assert "mâu thuẫn số học ngân sách" in result["critique_feedback"].lower()
