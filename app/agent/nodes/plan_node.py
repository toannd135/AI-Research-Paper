"""Node lập kế hoạch nghiên cứu: đề bài đã refine -> danh sách search sub-query."""

from app.agent.json_utils import parse_llm_json
from app.agent.state import ResearchState
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.gemini_adapter import DEFAULT_MODEL, GeminiAdapter

_SYSTEM_PROMPT = (
    "Bạn lập kế hoạch tìm kiếm tài liệu cho 1 câu hỏi nghiên cứu. "
    "Sinh 3-5 truy vấn tìm kiếm (search query) bao quát các khía cạnh/thuật ngữ khác nhau của câu hỏi, "
    "để tìm được tối đa các bài báo liên quan trong kho dữ liệu. "
    'Chỉ trả JSON: {"queries": ["...", "..."]}, không thêm text nào khác.'
)


def plan_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    question = state["question"]
    gateway = llm or GeminiAdapter()

    response = gateway.generate(
        messages=[
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=f"Câu hỏi nghiên cứu: {question}"),
        ],
        model_name=DEFAULT_MODEL,
    )

    parsed = parse_llm_json(response.text)
    queries: list[str] = []
    if isinstance(parsed, dict):
        queries = [q for q in parsed.get("queries", []) if isinstance(q, str) and q.strip()]

    if not queries:
        queries = [question]

    return {**state, "search_queries": queries}
