"""Evaluator baseline cho PaperAI Research Agent."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.schemas import Chunk, Citation


def compute_keyword_recall(answer: str, expected_keywords: list[str]) -> float:
    """Tính tỉ lệ từ khóa mong đợi xuất hiện trong câu trả lời."""
    if not expected_keywords:
        return 1.0
    if not answer:
        return 0.0

    answer_lower = answer.lower()
    matches = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return matches / len(expected_keywords)


def compute_paper_hit(state: dict[str, Any], expected_paper_ids: list[str]) -> float:
    """1.0 nếu có ít nhất 1 bài báo mong đợi nằm trong papers hoặc evidence, ngược lại 0.0."""
    if not expected_paper_ids:
        return 1.0

    found_ids: set[str] = set()
    for paper in state.get("papers", []):
        paper_id = (
            paper.paper_id if hasattr(paper, "paper_id") else paper.get("paper_id")
        )
        if paper_id:
            found_ids.add(paper_id)

    for chunk in state.get("evidence", []):
        paper_id = (
            chunk.paper_id if hasattr(chunk, "paper_id") else chunk.get("paper_id")
        )
        if paper_id:
            found_ids.add(paper_id)

    return 1.0 if any(pid in found_ids for pid in expected_paper_ids) else 0.0


def compute_citation_page_accuracy(
    citations: list[Citation], expected_pages: list[int]
) -> float:
    """Tính tỉ lệ citation có số trang khớp với expected_pages."""
    if not citations:
        return 0.0
    if not expected_pages:
        return 1.0

    correct = sum(
        1
        for c in citations
        if c.page_number is not None and c.page_number in expected_pages
    )
    return correct / len(citations)


def compute_citation_grounding(
    citations: list[Citation], evidence: list[Chunk]
) -> float:
    """Kiểm tra nghiêm ngặt 4 yếu tố grounding của Citation đối với Evidence:

    1. chunk_id tồn tại trong evidence
    2. paper_id khớp với chunk
    3. page_number khớp với chunk
    4. quoted_text là chuỗi con (substring) nằm trong chunk.content
    """
    if not citations:
        # Nếu không có citation và cũng không có evidence thì là grounded (chẳng hạn fallback)
        return 1.0 if not evidence else 0.0

    chunk_map: dict[str, Chunk] = {
        (c.chunk_id if hasattr(c, "chunk_id") else c["chunk_id"]): c for c in evidence
    }

    grounded_count = 0
    for cit in citations:
        c_id = cit.chunk_id if hasattr(cit, "chunk_id") else cit["chunk_id"]
        c_paper = cit.paper_id if hasattr(cit, "paper_id") else cit["paper_id"]
        c_page = (
            cit.page_number if hasattr(cit, "page_number") else cit.get("page_number")
        )
        c_quote = cit.quoted_text if hasattr(cit, "quoted_text") else cit["quoted_text"]

        if c_id not in chunk_map:
            continue

        chunk = chunk_map[c_id]
        orig_paper = chunk.paper_id if hasattr(chunk, "paper_id") else chunk["paper_id"]
        orig_page = (
            chunk.page_number
            if hasattr(chunk, "page_number")
            else chunk.get("page_number")
        )
        orig_content = chunk.content if hasattr(chunk, "content") else chunk["content"]

        # Kiểm tra đồng thời cả 4 điều kiện
        is_paper_valid = c_paper == orig_paper
        is_page_valid = c_page == orig_page
        is_quote_valid = c_quote.strip() in orig_content

        if is_paper_valid and is_page_valid and is_quote_valid:
            grounded_count += 1

    return grounded_count / len(citations)


def evaluate_single(
    question_item: dict[str, Any], result_state: dict[str, Any]
) -> dict[str, Any]:
    """Đánh giá 1 câu hỏi trên output của Agent."""
    answer = result_state.get("answer", "")
    citations = result_state.get("citations", [])
    evidence = result_state.get("evidence", [])

    kw_recall = compute_keyword_recall(
        answer, question_item.get("expected_answer_keywords", [])
    )
    paper_hit = compute_paper_hit(
        result_state, question_item.get("expected_paper_ids", [])
    )
    page_acc = compute_citation_page_accuracy(
        citations, question_item.get("expected_page_numbers", [])
    )
    grounding = compute_citation_grounding(citations, evidence)
    non_empty = 1.0 if answer.strip() else 0.0

    return {
        "id": question_item["id"],
        "keyword_recall": kw_recall,
        "paper_hit": paper_hit,
        "citation_page_accuracy": page_acc,
        "citation_grounding": grounding,
        "answer_non_empty": non_empty,
    }


def evaluate_batch(
    questions: list[dict[str, Any]], run_fn: Callable[[str], dict[str, Any]]
) -> dict[str, Any]:
    """Đánh giá toàn bộ tập câu hỏi và tổng hợp chỉ số trung bình."""
    detailed_scores: list[dict[str, Any]] = []

    for item in questions:
        result = run_fn(item["question"])
        scores = evaluate_single(item, result)
        detailed_scores.append(scores)

    n = len(detailed_scores)
    if n == 0:
        return {"avg_scores": {}, "detailed": []}

    avg_scores = {
        "avg_keyword_recall": sum(s["keyword_recall"] for s in detailed_scores) / n,
        "avg_paper_hit": sum(s["paper_hit"] for s in detailed_scores) / n,
        "avg_citation_page_accuracy": sum(
            s["citation_page_accuracy"] for s in detailed_scores
        )
        / n,
        "avg_citation_grounding": sum(s["citation_grounding"] for s in detailed_scores)
        / n,
        "avg_answer_non_empty": sum(s["answer_non_empty"] for s in detailed_scores) / n,
    }

    return {
        "avg_scores": avg_scores,
        "detailed": detailed_scores,
    }
