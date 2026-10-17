"""State chung cho LangGraph research pipeline."""

from typing import TypedDict

from app.core.schemas import Citation, ScoredChunk


class ResearchState(TypedDict, total=False):
    question: str
    search_queries: list[str]
    evidence: list[ScoredChunk]
    draft: str
    citations: list[Citation]
    critique_feedback: str | None
    iterations: int
    research_mode: str
    language: str  # mã ISO 639-1 của ngôn ngữ bài báo đầu ra (mặc định theo câu hỏi người dùng)
    baseline_analysis: str | None
    report: str
