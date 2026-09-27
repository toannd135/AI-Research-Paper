"""Node tổng hợp báo cáo cuối theo cấu trúc cố định."""

from app.agent.state import ResearchState
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.gemini_adapter import DEFAULT_MODEL, GeminiAdapter

_SYSTEM_PROMPT = (
    "Bạn tổng hợp draft nghiên cứu đã được kiểm chứng thành 1 báo cáo hoàn chỉnh. "
    "CHỈ dùng thông tin và trích dẫn [n] đã có trong draft, không thêm trích dẫn mới, "
    "không thêm thông tin ngoài draft. Giữ nguyên các đoạn [CẦN THÊM NGUỒN] nếu có.\n\n"
    "Trình bày đúng cấu trúc sau:\n"
    "# [Tiêu đề]\n\n## Tóm tắt\n...\n\n## 1. Giới thiệu\n...\n\n## 2. Tổng quan tài liệu\n...\n\n"
    "## 3. Thảo luận\n...\n\n## 4. Kết luận\n...\n\n## Tài liệu tham khảo\n"
    "(liệt kê từng [n] kèm paper_id/page/section tương ứng)"
)


def synthesize_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    citations = state.get("citations", [])
    references = "\n".join(
        f"[{i}] paper_id={c.paper_id}, page={c.page}, section={c.section}"
        for i, c in enumerate(citations, start=1)
    )

    gateway = llm or GeminiAdapter()
    response = gateway.generate(
        messages=[
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(
                role="user",
                content=(
                    f"Câu hỏi nghiên cứu: {state['question']}\n\n"
                    f"Draft đã kiểm chứng:\n{state.get('draft', '')}\n\n"
                    f"Danh sách trích dẫn hợp lệ:\n{references}"
                ),
            ),
        ],
        model_name=DEFAULT_MODEL,
    )

    return {**state, "report": response.text}
