"""Node tìm kiếm bài báo trong LangGraph."""

from __future__ import annotations

from app.agent.tools.search_papers import search_papers
from app.core.schemas import PaperRef, ResearchState


def search_node(state: ResearchState) -> dict:
    """Tìm kiếm các bài báo liên quan tới câu hỏi người dùng.

    Bắt buộc validate kết quả thô từ tool bằng PaperRef.model_validate().
    """
    question = state.get("question", "")
    raw_results = search_papers.invoke({"query": question})

    # Bắt buộc chuyển đổi và xác thực kiểu qua Pydantic model
    papers: list[PaperRef] = [PaperRef.model_validate(item) for item in raw_results]

    return {
        "papers": papers,
        "steps": ["search"],
    }
