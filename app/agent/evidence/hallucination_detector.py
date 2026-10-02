"""Phát hiện câu trong draft không có evidence hỗ trợ, bằng LLM-judge."""

from app.agent.json_utils import parse_llm_json
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.default import get_default_agent_gateway

_SYSTEM_PROMPT = (
    "Bạn là người kiểm chứng (fact-checker). So sánh từng câu trong draft với evidence được cung cấp. "
    "Chỉ ra những câu đưa ra thông tin/số liệu KHÔNG được evidence hỗ trợ (câu bịa hoặc suy diễn quá đà). "
    "Không tính các câu chuyển ý, câu hỏi mở, hoặc câu đã có đánh dấu [CẦN THÊM NGUỒN].\n\n"
    'Chỉ trả JSON: {"unsupported_sentences": ["...", "..."]}, mảng rỗng nếu draft đã được evidence hỗ trợ đầy đủ.'
)


def find_unsupported_sentences(
    draft: str, evidence_text: str, llm: LLMGateway | None = None
) -> list[str]:
    gateway, model_name = get_default_agent_gateway(llm)
    response = gateway.generate(
        messages=[
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=f"Evidence:\n{evidence_text}\n\nDraft:\n{draft}"),
        ],
        model_name=model_name,
    )

    parsed = parse_llm_json(response.text)
    if not isinstance(parsed, dict):
        return []
    sentences = parsed.get("unsupported_sentences", [])
    return [s for s in sentences if isinstance(s, str) and s.strip()]
