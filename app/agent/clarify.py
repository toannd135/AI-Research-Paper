"""Bước làm rõ đề bài — 1 lời gọi LLM đồng bộ trước khi vào graph nghiên cứu."""

from app.agent.json_utils import parse_llm_json
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.default import get_default_agent_gateway

_SYSTEM_PROMPT = (
    "Bạn giúp làm rõ một câu hỏi nghiên cứu trước khi hệ thống đi tìm tài liệu và viết báo cáo. "
    "Chỉ hỏi lại khi thực sự thiếu thông tin ảnh hưởng tới chất lượng kết quả "
    "(phạm vi câu hỏi, lĩnh vực, mục đích/độ dài báo cáo mong muốn). "
    "Tối đa 5 câu hỏi. Mỗi câu hỏi kèm 2-4 gợi ý trả lời ngắn gọn, cụ thể, khác biệt nhau, để "
    "người dùng có thể bấm chọn thay vì phải tự gõ. Nếu đã có clarification_answers hoặc câu hỏi "
    "đã đủ rõ, không hỏi lại nữa — hãy tự chọn giả định hợp lý nhất và đưa ra refined_question.\n\n"
    "Chỉ trả JSON theo đúng 1 trong 2 dạng sau, không thêm text nào khác:\n"
    '{"status": "needs_clarification", '
    '"questions": [{"text": "...", "suggestions": ["...", "..."]}]}\n'
    "hoặc\n"
    '{"status": "ready", "refined_question": "..."}'
)


def _parse_questions(raw: list) -> list[dict]:
    """Chuẩn hoá mỗi câu hỏi về {"text": str, "suggestions": list[str]}.

    LLM có thể trả thiếu field `suggestions` hoặc (lệch schema) trả thẳng chuỗi thay vì object —
    parse phòng thủ thay vì tin tuyệt đối theo schema đã yêu cầu trong prompt.
    """
    questions = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            questions.append({"text": item.strip(), "suggestions": []})
        elif isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
            suggestions = [s.strip() for s in item.get("suggestions", []) if isinstance(s, str) and s.strip()]
            questions.append({"text": item["text"].strip(), "suggestions": suggestions})
    return questions


def clarify(
    question: str,
    clarification_answers: dict[str, str] | None = None,
    llm: LLMGateway | None = None,
) -> dict:
    """Trả {"status": "needs_clarification", "questions": [...]} hoặc {"status": "ready", "refined_question": ...}.

    Mỗi entry trong "questions" là {"text": str, "suggestions": list[str]} — suggestions rỗng nếu
    LLM không sinh được gợi ý phù hợp, khi đó frontend fallback về ô nhập tự do.

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

    gateway, model_name = get_default_agent_gateway(llm)
    response = gateway.generate(
        messages=[
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ],
        model_name=model_name,
    )

    parsed = parse_llm_json(response.text)
    if not isinstance(parsed, dict) or parsed.get("status") not in {"needs_clarification", "ready"}:
        return {"status": "ready", "refined_question": question}

    if parsed["status"] == "needs_clarification" and not clarification_answers:
        questions = _parse_questions(parsed.get("questions") or [])
        if questions:
            return {"status": "needs_clarification", "questions": questions[:5]}

    return {"status": "ready", "refined_question": parsed.get("refined_question") or question}
