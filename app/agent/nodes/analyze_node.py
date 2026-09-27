"""Node phân tích evidence: build context + LLM viết draft có trích dẫn [n]."""

from app.agent.state import ResearchState
from app.ai.context_builder import build_context
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.gemini_adapter import DEFAULT_MODEL, GeminiAdapter

_SYSTEM_PROMPT = (
    "Bạn là trợ lý nghiên cứu khoa học. Chỉ viết dựa trên context được cung cấp, "
    "trích dẫn mỗi luận điểm bằng ký hiệu [n] khớp đúng với context. "
    "Không suy diễn hay dùng kiến thức ngoài context. Nếu context không đủ để trả lời một phần "
    "của câu hỏi, ghi rõ [CẦN THÊM NGUỒN] tại chỗ đó thay vì tự bịa."
)


def analyze_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    context_text, citations = build_context(state.get("evidence", []))

    user_content = f"Câu hỏi nghiên cứu: {state['question']}\n\nContext:\n{context_text}"
    feedback = state.get("critique_feedback")
    if feedback:
        user_content += f"\n\nPhản biện từ lần viết trước, hãy sửa lại: {feedback}"

    gateway = llm or GeminiAdapter()
    response = gateway.generate(
        messages=[
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ],
        model_name=DEFAULT_MODEL,
    )

    return {**state, "draft": response.text, "citations": citations}
