"""Bước làm rõ đề bài — 1 lời gọi LLM đồng bộ trước khi vào graph nghiên cứu."""

from app.agent.json_utils import parse_llm_json
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.gemini_adapter import DEFAULT_MODEL, GeminiAdapter

_SYSTEM_PROMPT = (
    "Bạn giúp làm rõ một câu hỏi nghiên cứu trước khi hệ thống đi tìm tài liệu và viết báo cáo. "
    "Chỉ hỏi lại khi thực sự thiếu thông tin ảnh hưởng tới chất lượng kết quả "
    "(phạm vi câu hỏi, lĩnh vực, mục đích/độ dài báo cáo mong muốn). "
    "Tối đa 5 câu hỏi. Nếu đã có clarification_answers hoặc câu hỏi đã đủ rõ, không hỏi lại nữa — "
    "hãy tự chọn giả định hợp lý nhất và đưa ra refined_question.\n\n"
    "Chỉ trả JSON theo đúng 1 trong 2 dạng sau, không thêm text nào khác:\n"
    '{"status": "needs_clarification", "questions": ["...", "..."]}\n'
    'hoặc\n'
    '{"status": "ready", "refined_question": "..."}'
)


def clarify(
    question: str,
    clarification_answers: dict[str, str] | None = None,
    llm: LLMGateway | None = None,
) -> dict:
    """Trả {"status": "needs_clarification", "questions": [...]} hoặc {"status": "ready", "refined_question": ...}.

    Chỉ hỏi lại khi clarification_answers chưa được cung cấp — nếu client đã trả lời (dù vẫn còn
    thiếu), hệ thống không hỏi thêm vòng nữa để tránh lặp vô hạn, mà tự chọn giả định hợp lý.
    """
    if clarification_answers:
        user_content = (
            f"Câu hỏi gốc: {question}\n"
            f"Client đã trả lời làm rõ: {clarification_answers}\n"
            "Hãy tổng hợp thành refined_question, không hỏi lại nữa."
        )
    else:
        user_content = f"Câu hỏi gốc: {question}"

    gateway = llm or GeminiAdapter()
    response = gateway.generate(
        messages=[
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ],
        model_name=DEFAULT_MODEL,
    )

    parsed = parse_llm_json(response.text)
    if not isinstance(parsed, dict) or parsed.get("status") not in {"needs_clarification", "ready"}:
        return {"status": "ready", "refined_question": question}

    if parsed["status"] == "needs_clarification" and not clarification_answers:
        questions = parsed.get("questions") or []
        if questions:
            return {"status": "needs_clarification", "questions": questions[:5]}

    return {"status": "ready", "refined_question": parsed.get("refined_question") or question}
