"""Node fallback khi không tìm thấy đủ bằng chứng."""

from __future__ import annotations

from app.core.schemas import ResearchState

FALLBACK_MESSAGE = "Không tìm thấy đủ bằng chứng để trả lời câu hỏi."


def fallback_node(state: ResearchState) -> dict:
    """Fallback an toàn khi không có evidence, chống hallucination."""
    return {
        "answer": FALLBACK_MESSAGE,
        "citations": [],
        "steps": ["fallback"],
    }
