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
    report: str
