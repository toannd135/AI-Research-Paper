"""Node dựng Research Knowledge Model: trích gaps / research questions / claims từ phân tích rồi kiểm chứng với evidence."""

import logging

from app.agent.evidence.claim_validator import validate_model
from app.agent.json_utils import parse_llm_json
from app.agent.research_model import build_research_model, contribution_profile
from app.agent.state import ResearchState
from app.ai.llm_gateway.base import LLMGateway, LLMGatewayError, Message
from app.ai.llm_gateway.default import get_default_agent_gateway

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Bạn xây dựng Research Knowledge Model cho một bài báo khoa học từ bản phân tích và danh sách nguồn.\n"
    "Trích xuất, CHỈ dựa vào nội dung được cung cấp (không bịa số liệu, không bịa nguồn):\n"
    "- research_gaps: các khoảng trống nghiên cứu, mỗi mục {\"text\", \"evidence_refs\": [số [n] của nguồn chứng minh khoảng trống đó]}.\n"
    "- research_questions: các câu hỏi/giả thuyết nghiên cứu (chuỗi).\n"
    "- claims: các khẳng định đóng góp của bài, mỗi mục {\"text\", \"kind\": \"performance\"|\"efficiency\"|\"novelty\"|\"generalization\"|\"other\", "
    "\"source\": \"literature\" (kết quả đã công bố trong nguồn) | \"user_results\" (kết quả người dùng cung cấp) | \"proposed\" (dự kiến, chưa đo), "
    "\"baseline\", \"metric\", \"dataset\" (null nếu không có), \"evidence_refs\": [số [n]]}.\n"
    "- experiments: chỉ khi người dùng cung cấp số liệu từng lần chạy (seed/fold): mỗi mục {\"system\", \"role\": \"proposed\"|\"baseline\", \"metric\", "
    "\"dataset\", \"values\": [số của từng lần chạy, chép nguyên văn]}. Không có số liệu thì để mảng rỗng.\n"
    "Claim so sánh hiệu năng/hiệu quả phải ghi rõ baseline, metric, dataset nếu thông tin có trong nội dung; nếu không có thì để null, ĐỪNG đoán.\n"
    'Chỉ trả JSON: {"research_gaps": [...], "research_questions": [...], "claims": [...], "experiments": [...]}, không thêm text nào khác.'
)


def model_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    citations = state.get("citations", [])
    parsed = None
    if contribution_profile(state)["mode"] != "survey" or state.get("user_results"):
        user_content = (
            f"Câu hỏi nghiên cứu: {state['question']}\n"
            f"Loại đóng góp: {contribution_profile(state)['label']}\n"
            f"Số nguồn hợp lệ: {len(citations)} (chỉ dùng evidence_refs trong khoảng 1..{len(citations)})\n\n"
            f"Bản phân tích:\n{state.get('draft', '')}\n"
        )
        if state.get("user_results"):
            user_content += f"\nKẾT QUẢ THỰC NGHIỆM DO NGƯỜI DÙNG CUNG CẤP (source=user_results):\n{state['user_results']}\n"
        try:
            gateway, model_name = get_default_agent_gateway(llm)
            response = gateway.generate(
                messages=[Message(role="system", content=_SYSTEM_PROMPT), Message(role="user", content=user_content)],
                model_name=model_name,
            )
            parsed = parse_llm_json(response.text)
        except LLMGatewayError:
            logger.warning("Không trích xuất được Research Knowledge Model, bỏ qua claim validation", exc_info=True)

    model = validate_model(build_research_model(state, parsed), len(citations))
    return {**state, "research_model": model}
