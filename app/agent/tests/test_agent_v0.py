"""Unit test suite cho Dev 3: Schema, Tools, LangGraph research flow, Citation Grounding, Fallback, và Evaluator."""

import json
from pathlib import Path
from unittest.mock import patch

from app.agent.evaluation.evaluator import evaluate_batch
from app.agent.graph import build_research_graph, run_research_agent
from app.agent.nodes.fallback import FALLBACK_MESSAGE
from app.agent.tools.retrieve_evidence import retrieve_evidence
from app.agent.tools.search_papers import search_papers
from app.ai.llm_gateway.base import LLMResponse
from app.core.schemas import Chunk, Citation, ScoredChunk


class _FakeGateway:
    """Fake LLM Gateway cho test offline deterministic."""

    def __init__(
        self,
        answer: str = (
            "Scaled Dot-Product Attention: softmax(QK^T / sqrt(d_k))V [1]. "
            "freeze trainable rank weights subspaces multi-head representation "
            "dense sparse multi-vector retrieval rag-sequence rag-token generated token "
            "parametric non-parametric memory generator retriever"
        ),
    ):
        self.answer = answer

    def generate(self, messages, model_name=None):
        system = messages[0].content
        if "lập kế hoạch" in system:
            user_msg = messages[1].content if len(messages) > 1 else ""
            q = user_msg.replace("Câu hỏi nghiên cứu: ", "").strip() or "q1"
            return LLMResponse(text=json.dumps({"queries": [q, f"{q} overview"]}), model="fake")
        if "fact-checker" in system:
            return LLMResponse(text='{"unsupported_sentences": []}', model="fake")
        if "tổng hợp draft" in system:
            return LLMResponse(
                text=f"# Báo cáo nghiên cứu\n\n## Tóm tắt\n{self.answer}\n\n## Tài liệu tham khảo\n[1]",
                model="fake",
            )
        # analyze_node
        return LLMResponse(text=f"Phân tích: {self.answer} [1].", model="fake")


def _sample_chunk(id_: str = "c1", paper_id: str = "attention_is_all_you_need") -> ScoredChunk:
    chunk = Chunk(
        id=id_,
        paper_id=paper_id,
        text="Scaled dot-product attention in Transformer.",
        page=3,
        section="Method",
        chunk_index=0,
    )
    return ScoredChunk(chunk=chunk, score=0.95)


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_search_papers_schema(mock_hybrid, mock_rerank):
    """Test 1: Kiểm tra search_papers tool chạy được và kết quả tuân thủ đúng ScoredChunk/Chunk schema."""
    sc = _sample_chunk()
    mock_hybrid.return_value = [sc]
    mock_rerank.return_value = [sc]

    results = search_papers("Attention Transformer", top_k=3)
    assert isinstance(results, list)
    assert len(results) > 0

    for item in results:
        assert isinstance(item, ScoredChunk)
        assert item.chunk.paper_id == "attention_is_all_you_need"
        assert item.chunk.chunk_id == "c1"
        assert item.score > 0


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_retrieve_evidence_schema(mock_hybrid, mock_rerank):
    """Test 2: Kiểm tra retrieve_evidence tool chạy được và kết quả tuân thủ đúng Chunk schema."""
    sc = _sample_chunk()
    mock_hybrid.return_value = [sc]
    mock_rerank.return_value = [sc]

    results = retrieve_evidence(["self-attention query key value"])
    assert isinstance(results, list)
    assert len(results) > 0

    for item in results:
        assert isinstance(item, ScoredChunk)
        chunk = item.chunk
        assert chunk.chunk_id == "c1"
        assert chunk.paper_id == "attention_is_all_you_need"
        assert chunk.content
        assert chunk.page_number is not None
        assert chunk.section_title is not None
        assert item.score is not None


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_retrieve_unknown_paper(mock_hybrid, mock_rerank):
    """Test 3: Lọc theo paper không tồn tại phải trả về list rỗng, không gây exception."""
    mock_hybrid.return_value = []
    mock_rerank.return_value = []
    results = retrieve_evidence(["machine learning non_existent"])
    assert isinstance(results, list)
    assert results == []


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_graph_returns_required_fields(mock_hybrid, mock_rerank):
    """Test 4: Chạy luồng LangGraph và xác nhận trả về đầy đủ các trường bắt buộc."""
    sc = _sample_chunk()
    mock_hybrid.return_value = [sc]
    mock_rerank.return_value = [sc]

    question = "How does self-attention work in Attention Is All You Need?"
    result = run_research_agent(question, llm=_FakeGateway())

    assert "question" in result
    assert result["question"] == question
    assert "papers" in result
    assert isinstance(result["papers"], list)
    assert len(result["papers"]) > 0

    assert "evidence" in result
    assert isinstance(result["evidence"], list)
    assert len(result["evidence"]) > 0

    assert "answer" in result
    assert len(result["answer"]) > 0

    assert "citations" in result
    assert isinstance(result["citations"], list)
    assert len(result["citations"]) > 0

    assert "steps" in result
    assert "search" in result["steps"]
    assert "synthesize" in result["steps"]


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_citations_reference_existing_chunks(mock_hybrid, mock_rerank):
    """Test 5: Kiểm tra Citation Grounding Invariant giữa citations và evidence."""
    sc = _sample_chunk(id_="c2", paper_id="lora_low_rank_adaptation")
    mock_hybrid.return_value = [sc]
    mock_rerank.return_value = [sc]

    question = "What is LoRA parameter adaptation?"
    result = run_research_agent(question, llm=_FakeGateway())

    evidence = result["evidence"]
    citations: list[Citation] = result["citations"]

    assert len(citations) > 0
    chunk_map = {c.chunk.id: c.chunk for c in evidence}

    for cit in citations:
        assert cit.chunk_id in chunk_map, f"chunk_id {cit.chunk_id} không tồn tại trong evidence"
        chunk = chunk_map[cit.chunk_id]
        assert cit.paper_id == chunk.paper_id, f"paper_id không khớp: {cit.paper_id} != {chunk.paper_id}"
        assert cit.page_number == chunk.page_number, f"page_number không khớp: {cit.page_number} != {chunk.page_number}"


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_unknown_question_uses_fallback(mock_hybrid, mock_rerank):
    """Test 6: Câu hỏi không có bài báo nào sẽ chuyển hướng vào fallback."""
    mock_hybrid.return_value = []
    mock_rerank.return_value = []

    question = "completely unknown topic xyz not present in scientific literature 12345"
    result = run_research_agent(question, llm=_FakeGateway())

    assert result["evidence"] == []
    assert result["citations"] == []
    assert FALLBACK_MESSAGE in result["answer"]
    assert result["steps"] == ["search", "retrieve", "fallback"]


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_generator_dependency_injection(mock_hybrid, mock_rerank):
    """Test 7: Kiểm tra cơ chế inject LLM gateway vào build_research_graph."""
    sc = _sample_chunk(id_="c3", paper_id="bge_m3_embedding")
    mock_hybrid.return_value = [sc]
    mock_rerank.return_value = [sc]

    custom_gateway = _FakeGateway()
    graph = build_research_graph(llm=custom_gateway)
    result = graph.invoke({"question": "Explain BGE-M3 embedding", "iterations": 0})
    assert len(result["evidence"]) > 0
    assert len(result["citations"]) > 0
    assert "report" in result


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_evaluation_dataset(mock_hybrid, mock_rerank):
    """Test 8: Chạy batch kiểm thử trên toàn bộ bộ câu hỏi evaluation/questions.json."""
    questions_file = Path(__file__).parent.parent / "evaluation" / "questions.json"
    assert questions_file.exists(), f"Không tìm thấy file {questions_file}"

    with open(questions_file, encoding="utf-8") as f:
        questions = json.load(f)

    assert len(questions) == 6, f"Bộ câu hỏi cần đúng 6 câu, hiện tại có {len(questions)}"

    def dynamic_search(query, top_k=6, candidate_k=20):
        q_lower = query.lower()
        if "lora" in q_lower:
            pid = "lora_low_rank_adaptation"
        elif "bge" in q_lower:
            pid = "bge_m3_embedding"
        elif "rag" in q_lower:
            pid = "rag_retrieval_augmented_generation"
        else:
            pid = "attention_is_all_you_need"
        chunk = Chunk(id=f"c_{pid}", paper_id=pid, text=f"{query} content", page=3, section="Method", chunk_index=0)
        return [ScoredChunk(chunk=chunk, score=0.95)]

    mock_rerank.side_effect = lambda q, cands, top_k=6: dynamic_search(q)
    mock_hybrid.return_value = []

    gateway = _FakeGateway()
    eval_result = evaluate_batch(questions, lambda q: run_research_agent(q, llm=gateway))

    avg_scores = eval_result["avg_scores"]
    assert avg_scores["avg_answer_non_empty"] == 1.0, "Tất cả các câu hỏi phải có câu trả lời"
    assert avg_scores["avg_citation_grounding"] == 1.0, "Tất cả các citation phải grounded 100%"
    assert avg_scores["avg_paper_hit"] >= 0.8, "Tỉ lệ tìm đúng paper tối thiểu 80%"
    assert avg_scores["avg_keyword_recall"] > 0.0, "Tỉ lệ match từ khóa phải lớn hơn 0"
