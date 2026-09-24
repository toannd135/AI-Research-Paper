"""Unit test suite cho Dev 3 Tuần 1: Schema, Mock Tools, LangGraph v0, Citation Grounding, Fallback, và Evaluator."""

import json
from pathlib import Path

from app.agent.evaluation.evaluator import evaluate_batch
from app.agent.generators.mock import MockAnswerGenerator
from app.agent.graph import build_research_graph, run_research_agent
from app.agent.nodes.fallback import FALLBACK_MESSAGE
from app.agent.tools.retrieve_evidence import retrieve_evidence
from app.agent.tools.search_papers import search_papers
from app.core.schemas import Chunk, Citation, PaperRef


def test_search_papers_schema():
    """Test 1: Kiểm tra search_papers tool chạy được và kết quả tuân thủ đúng PaperRef schema."""
    results = search_papers.invoke({"query": "Attention Transformer", "top_k": 3})
    assert isinstance(results, list)
    assert len(results) > 0

    for item in results:
        # Bắt buộc validate thành công theo Pydantic model PaperRef
        paper = PaperRef.model_validate(item)
        assert paper.paper_id
        assert paper.title
        assert isinstance(paper.authors, list)
        assert paper.year is not None


def test_retrieve_evidence_schema():
    """Test 2: Kiểm tra retrieve_evidence tool chạy được và kết quả tuân thủ đúng Chunk schema."""
    results = retrieve_evidence.invoke(
        {
            "query": "self-attention query key value",
            "paper_id": "attention_is_all_you_need",
            "top_k": 3,
        }
    )
    assert isinstance(results, list)
    assert len(results) > 0

    for item in results:
        # Bắt buộc validate thành công theo Pydantic model Chunk
        chunk = Chunk.model_validate(item)
        assert chunk.chunk_id
        assert chunk.paper_id == "attention_is_all_you_need"
        assert chunk.content
        assert chunk.page_number is not None
        assert chunk.section_title is not None
        assert chunk.score is not None


def test_retrieve_unknown_paper():
    """Test 3: Lọc theo paper_id không tồn tại phải trả về list rỗng, không gây exception."""
    results = retrieve_evidence.invoke(
        {"query": "machine learning", "paper_id": "non_existent_paper_id_9999"}
    )
    assert isinstance(results, list)
    assert results == []


def test_graph_returns_required_fields():
    """Test 4: Chạy luồng LangGraph và xác nhận trả về đầy đủ các trường bắt buộc và steps tích lũy qua reducer."""
    question = "How does self-attention work in Attention Is All You Need?"
    result = run_research_agent(question)

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
    # Kiểm tra reducer đã tích lũy đúng thứ tự các bước
    assert result["steps"] == ["search", "retrieve", "synthesize"]


def test_citations_reference_existing_chunks():
    """Test 5: Kiểm tra nghiêm ngặt 4 yếu tố Citation Grounding Invariant:

    1. citation.chunk_id nằm trong evidence
    2. citation.paper_id khớp với chunk
    3. citation.page_number khớp với chunk
    4. citation.quoted_text là chuỗi con (substring) nằm trong chunk.content
    """
    question = "What is LoRA parameter adaptation?"
    result = run_research_agent(question)

    evidence: list[Chunk] = result["evidence"]
    citations: list[Citation] = result["citations"]

    assert len(citations) > 0
    chunk_map = {c.chunk_id: c for c in evidence}

    for cit in citations:
        # 1. chunk_id tồn tại trong evidence
        assert cit.chunk_id in chunk_map, (
            f"chunk_id {cit.chunk_id} không tồn tại trong evidence"
        )

        chunk = chunk_map[cit.chunk_id]
        # 2. paper_id khớp
        assert cit.paper_id == chunk.paper_id, (
            f"paper_id không khớp: {cit.paper_id} != {chunk.paper_id}"
        )
        # 3. page_number khớp
        assert cit.page_number == chunk.page_number, (
            f"page_number không khớp: {cit.page_number} != {chunk.page_number}"
        )
        # 4. quoted_text là chuỗi con thực sự
        assert cit.quoted_text.strip() in chunk.content, (
            f"quoted_text '{cit.quoted_text}' không nằm trong chunk.content"
        )


def test_unknown_question_uses_fallback():
    """Test 6: Câu hỏi hoàn toàn lạ không có bài báo nào sẽ chuyển hướng vào fallback_node."""
    question = "completely unknown topic xyz not present in scientific literature 12345"
    result = run_research_agent(question)

    assert result["evidence"] == []
    assert result["citations"] == []
    assert FALLBACK_MESSAGE in result["answer"]
    # Kiểm tra steps rẽ nhánh vào fallback
    assert result["steps"] == ["search", "retrieve", "fallback"]


def test_generator_dependency_injection():
    """Test bổ sung: Kiểm tra cơ chế inject AnswerGenerator qua closure factory."""
    custom_generator = MockAnswerGenerator()
    graph = build_research_graph(generator=custom_generator)
    result = graph.invoke(
        {
            "question": "Explain BGE-M3 embedding",
            "papers": [],
            "evidence": [],
            "answer": "",
            "citations": [],
            "steps": [],
        }
    )
    assert len(result["evidence"]) > 0
    assert len(result["citations"]) > 0
    assert result["steps"] == ["search", "retrieve", "synthesize"]


def test_evaluation_dataset():
    """Test 7: Chạy batch kiểm thử trên toàn bộ bộ câu hỏi evaluation/questions.json v0."""
    questions_file = Path(__file__).parent.parent / "evaluation" / "questions.json"
    assert questions_file.exists(), f"Không tìm thấy file {questions_file}"

    with open(questions_file, encoding="utf-8") as f:
        questions = json.load(f)

    assert len(questions) == 6, (
        f"Bộ câu hỏi cần đúng 6 câu, hiện tại có {len(questions)}"
    )

    # Chạy batch evaluation
    eval_result = evaluate_batch(questions, run_research_agent)

    avg_scores = eval_result["avg_scores"]
    assert avg_scores["avg_answer_non_empty"] == 1.0, (
        "Tất cả các câu hỏi phải có câu trả lời"
    )
    assert avg_scores["avg_citation_grounding"] == 1.0, (
        "Tất cả các citation phải grounded 100%"
    )
    assert avg_scores["avg_paper_hit"] >= 0.8, "Tỉ lệ tìm đúng paper tối thiểu 80%"
    assert avg_scores["avg_keyword_recall"] > 0.0, "Tỉ lệ match từ khóa phải lớn hơn 0"
