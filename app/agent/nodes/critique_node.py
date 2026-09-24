"""Node tự phản biện kết quả: kiểm tra citation hợp lệ + câu không có evidence hỗ trợ."""

from app.agent.evidence.citation_validator import find_invalid_citations
from app.agent.evidence.hallucination_detector import find_unsupported_sentences
from app.agent.state import ResearchState
from app.ai.context_builder import build_context
from app.ai.llm_gateway.base import LLMGateway


def critique_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    draft = state.get("draft", "")
    citations = state.get("citations", [])
    evidence_text, _ = build_context(state.get("evidence", []))

    invalid_citations = find_invalid_citations(draft, citations)
    unsupported = find_unsupported_sentences(draft, evidence_text, llm=llm)

    iterations = state.get("iterations", 0) + 1

    if not invalid_citations and not unsupported:
        return {**state, "critique_feedback": None, "iterations": iterations}

    feedback_parts = []
    if invalid_citations:
        feedback_parts.append(f"Các trích dẫn không hợp lệ: {invalid_citations}")
    if unsupported:
        feedback_parts.append(
            "Các câu sau không có evidence hỗ trợ, hãy sửa lại hoặc đánh dấu [CẦN THÊM NGUỒN]: "
            + " | ".join(unsupported)
        )

    return {**state, "critique_feedback": "\n".join(feedback_parts), "iterations": iterations}
