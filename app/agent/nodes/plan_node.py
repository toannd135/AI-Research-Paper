"""Node lập kế hoạch nghiên cứu: phân loại intent (survey vs novel_research) và sinh search queries đa chiều."""

from app.agent.json_utils import parse_llm_json
from app.agent.profiles import FIELD_PROFILES, detect_field, normalize_field
from app.agent.research_model import (
    CONTRIBUTION_TYPES,
    METHODOLOGIES,
    PAPER_TYPES,
    contribution_from_mode,
    normalize_choice,
    normalize_contribution,
)
from app.agent.state import ResearchState
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.default import get_default_agent_gateway

_SYSTEM_PROMPT = (
    "Bạn lập kế hoạch tìm kiếm tài liệu cho 1 bài toán/câu hỏi nghiên cứu khoa học.\n"
    "1. Xác định chế độ nghiên cứu ('mode'):\n"
    "   - 'novel_research': nếu câu hỏi yêu cầu cải tiến một mô hình/đề tài cụ thể, đề xuất kiến trúc/thuật toán mới, khắc phục nhược điểm của baseline.\n"
    "   - 'survey': nếu câu hỏi yêu cầu tổng quan, phân tích tổng hợp các nghiên cứu hiện có, khảo sát hiện trạng.\n"
    "2. Sinh 4-5 truy vấn tìm kiếm (search queries) chuyên sâu bao quát 5 khía cạnh cốt lõi:\n"
    "   - [Khía cạnh 1]: Các công trình cội nguồn và cơ chế hoạt động cốt lõi (Seminal & Foundational Baselines). Hãy đưa thẳng tên các bài báo cội nguồn đầu tiên định nghĩa hiện tượng hoặc mô hình gốc (ví dụ: với Position Bias/LLM-as-a-Judge: 'Zheng Judging LLM-as-a-Judge MT-Bench', 'Wang Large Language Models are not Fair Evaluators', 'Zeng LLMBar', 'Bai HH-RLHF Anthropic'; với RAG: 'IRCoT Trivedi', 'Self-RAG Asai', 'CoVe Dhuliawala') để kéo chính xác bài báo gốc trước khi so sánh.\n"
    "   - [Khía cạnh 2]: Bộ dữ liệu chuẩn (Benchmark Datasets), phương pháp đánh giá (Metrics/Evaluation Protocols).\n"
    "   - [Khía cạnh 3]: Các điểm nghẽn, nhược điểm và failure modes của các phương pháp hiện tại (Bottlenecks & Limitations).\n"
    "   - [Khía cạnh 4]: Các hướng tiếp cận tiên tiến, công thức toán học hoặc kỹ thuật kết hợp (Advanced/Cross-domain Techniques).\n"
    "   - [Khía cạnh 5]: So sánh định lượng và kết quả thực nghiệm SOTA (Empirical Benchmark Comparisons).\n"
    "Mọi truy vấn tìm kiếm PHẢI viết bằng tiếng Anh (kho bài báo quốc tế), dù câu hỏi dùng ngôn ngữ nào.\n"
    f"3. Xác định lĩnh vực ('field'), một trong: {', '.join(FIELD_PROFILES)}.\n"
    "4. Phân loại đóng góp khoa học ('contribution_type'), một trong: "
    "'new_method' (đề xuất mô hình/phương pháp mới), 'improvement' (cải tiến phương pháp có sẵn: nhanh hơn, nhẹ hơn, chính xác hơn), "
    "'comparison' (so sánh nhiều mô hình/phương pháp trên cùng dataset), 'system' (xây dựng/triển khai hệ thống thực tế), "
    "'survey' (tổng quan, khảo sát). Kèm 'methodology' (một trong: " + ", ".join(METHODOLOGIES) + "), "
    "'paper_type' (một trong: " + ", ".join(PAPER_TYPES) + ") và 'topic' (chủ đề ngắn gọn bằng tiếng Anh).\n"
    'Chỉ trả lời định dạng JSON hợp lệ: {"mode": "survey" | "novel_research", "field": "...", "contribution_type": "...", '
    '"methodology": "...", "paper_type": "...", "topic": "...", "queries": ["...", "..."]}, không thêm text nào khác.'
)


def detect_research_mode(question: str, parsed_mode: str | None = None) -> str:
    """Xác định chế độ nghiên cứu: 'novel_research' hoặc 'survey'."""
    if parsed_mode in ("novel_research", "survey"):
        return parsed_mode

    q_lower = question.lower()
    novelty_keywords = [
        "cải tiến", "đề xuất", "mô hình mới", "kiến trúc mới", "thuật toán mới",
        "novel", "improve", "improvement", "propose", "proposal", "new architecture",
        "phát triển bài báo mới", "thiết kế mới", "vượt trội", "khắc phục nhược điểm",
        "sáng tạo", "baseline", "cải tiến đề tài", "cải tiến mô hình", "tự nghiên cứu và phát triển"
    ]
    if any(k in q_lower for k in novelty_keywords):
        return "novel_research"
    return "survey"


def plan_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    question = state["question"]
    gateway, model_name = get_default_agent_gateway(llm)

    response = gateway.generate(
        messages=[
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=f"Câu hỏi nghiên cứu: {question}"),
        ],
        model_name=model_name,
    )

    parsed = parse_llm_json(response.text)
    queries: list[str] = []
    detected_mode = None
    detected_field = None
    parsed_dict: dict = parsed if isinstance(parsed, dict) else {}

    if isinstance(parsed, dict):
        queries = [q for q in parsed.get("queries", []) if isinstance(q, str) and q.strip()]
        detected_mode = parsed.get("mode")
        detected_field = normalize_field(parsed.get("field")) if isinstance(parsed.get("field"), str) else None

    if not queries:
        from app.ai.external.query_rewrite import to_english_search_query

        queries = [to_english_search_query(question, gateway, model_name)]

    # Người dùng chọn contribution_type thì ưu tiên; nếu không dùng kết quả LLM, rồi mới suy ra từ mode.
    contribution = normalize_contribution(state.get("contribution_type")) or normalize_contribution(parsed_dict.get("contribution_type"))
    if contribution:
        mode = CONTRIBUTION_TYPES[contribution]["mode"]
    else:
        mode = detect_research_mode(question, detected_mode)
        contribution = contribution_from_mode(mode)
    profile = CONTRIBUTION_TYPES[contribution]

    field = normalize_field(state.get("field")) or detected_field or detect_field(question)
    topic = parsed_dict.get("topic") if isinstance(parsed_dict.get("topic"), str) and parsed_dict["topic"].strip() else question

    return {
        **state,
        "search_queries": queries,
        "research_mode": mode,
        "field": field,
        "contribution_type": contribution,
        "methodology": normalize_choice(parsed_dict.get("methodology"), METHODOLOGIES, profile["methodology"]),
        "paper_type": normalize_choice(parsed_dict.get("paper_type"), PAPER_TYPES, profile["paper_type"]),
        "topic": topic.strip(),
    }
