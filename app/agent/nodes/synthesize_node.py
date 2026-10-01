"""Node tổng hợp báo cáo cuối theo chuẩn cấu trúc IMRaD."""

from app.agent.state import ResearchState
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.gemini_adapter import DEFAULT_MODEL, GeminiAdapter

_SYSTEM_PROMPT = (
    "Bạn tổng hợp draft nghiên cứu đã được kiểm chứng thành 1 báo cáo khoa học hoàn chỉnh theo chuẩn cấu trúc IMRaD.\n"
    "CHỈ dùng thông tin và trích dẫn [n] đã có trong draft/references, không thêm trích dẫn mới, "
    "không thêm thông tin ngoài draft. Giữ nguyên các đoạn [CẦN THÊM NGUỒN] nếu có.\n\n"
    "Quy tắc quan trọng trong từng phần:\n"
    "- Abstract: tự đứng độc lập, KHÔNG chứa trích dẫn [n], không viết tắt khi chưa định nghĩa. Cần thể hiện rõ: [Context] [Problem] [Method] [Key results] [Implication].\n"
    "- Introduction: triển khai theo dạng 'phễu' (rộng -> hẹp -> khoảng trống nghiên cứu -> 3–4 gạch đầu dòng contributions chính).\n"
    "- Methodology: nêu rõ bài toán, công thức toán học (nếu có), giả thuật (pseudo-code) hoặc các bước xử lý. BẮT BUỘC sử dụng khối mã Mermaid (```mermaid ... ```) để vẽ sơ đồ kiến trúc hệ thống hoặc luồng hoạt động trực quan.\n"
    "- Experiments and Results: trình bày số liệu thực nghiệm, kết quả so sánh, mọi bảng biểu/sơ đồ phải được nhắc đến trong văn bản.\n"
    "- Discussion: phân tích sâu kết quả (Analysis), thừa nhận hạn chế (Limitations) và nguy cơ sai lệch (Threats to validity).\n"
    "- Trích dẫn: mọi khẳng định lấy từ tài liệu đều phải có citation [n] tương ứng; tuyệt đối không bịa tài liệu tham khảo.\n"
    "- Văn phong: học thuật khách quan, thì hiện tại cho sự thật chung, thì quá khứ cho công việc đã làm, hạn chế từ cảm tính.\n\n"
    "Trình bày ĐÚNG theo mẫu Markdown sau:\n"
    "# [Title]\n\n"
    "**Authors:** [Tên tác giả / Nhóm tác giả] | **Affiliations:** [Đơn vị nghiên cứu / Lab]\n\n"
    "## Abstract\n"
    "[Context] ... [Problem] ... [Method] ... [Key results] ... [Implication] ...\n\n"
    "**Keywords:** k1, k2, k3\n\n"
    "## 1. Introduction\n"
    "### 1.1 Background\n"
    "...\n"
    "### 1.2 Problem statement & research gap\n"
    "...\n"
    "### 1.3 Contributions\n"
    "- Contribution 1\n"
    "- Contribution 2\n"
    "- Contribution 3\n\n"
    "### 1.4 Paper organization\n"
    "...\n\n"
    "## 2. Related Work\n"
    "...\n\n"
    "## 3. Methodology\n"
    "### 3.1 Problem formulation\n"
    "...\n"
    "### 3.2 Proposed approach\n"
    "```mermaid\n"
    "graph TD\n"
    "...\n"
    "```\n"
    "...\n"
    "### 3.3 Implementation details\n"
    "...\n\n"
    "## 4. Experiments and Results\n"
    "### 4.1 Datasets\n"
    "...\n"
    "### 4.2 Baselines & metrics\n"
    "...\n"
    "### 4.3 Main results\n"
    "...\n"
    "### 4.4 Ablation study\n"
    "...\n\n"
    "## 5. Discussion\n"
    "### 5.1 Analysis\n"
    "...\n"
    "### 5.2 Limitations\n"
    "...\n"
    "### 5.3 Threats to validity\n"
    "...\n\n"
    "## 6. Conclusion and Future Work\n"
    "...\n\n"
    "## Acknowledgments\n"
    "...\n\n"
    "## References\n"
    "(Liệt kê chi tiết từng [n] theo danh sách trích dẫn hợp lệ được cung cấp)\n\n"
    "## Appendix\n"
    "..."
)


def synthesize_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    citations = state.get("citations", [])
    references_lines = []
    for i, c in enumerate(citations, start=1):
        ref_line = f"[{i}] {c.paper_id}"
        if c.page:
            ref_line += f", Page: {c.page}"
        if c.section:
            ref_line += f", Section: {c.section}"
        if c.text_snippet:
            clean_snippet = c.text_snippet.replace("\n", " ").strip()[:150]
            ref_line += f' — "{clean_snippet}..."'
        references_lines.append(ref_line)
    references = "\n".join(references_lines)

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
