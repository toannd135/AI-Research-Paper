"""Node tổng hợp câu trả lời và trích dẫn bằng chứng."""

from __future__ import annotations

from collections.abc import Callable

from app.agent.generators.base import AnswerGenerator
from app.core.schemas import ResearchState


def create_synthesize_node(
    generator: AnswerGenerator,
) -> Callable[[ResearchState], dict]:
    """Factory closure tạo synthesize_node với dependency injection cho AnswerGenerator."""

    def synthesize_node(state: ResearchState) -> dict:
        question = state.get("question", "")
        evidence = state.get("evidence", [])

        answer, citations = generator.generate(question=question, evidence=evidence)

        return {
            "answer": answer,
            "citations": citations,
            "steps": ["synthesize"],
        }

    return synthesize_node
