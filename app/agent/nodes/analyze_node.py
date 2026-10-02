"""Node phân tích evidence: xây dựng context học thuật, tổng hợp chuyên sâu và đề xuất giải pháp."""

from app.agent.format_sanitizer import sanitize_academic_markdown
from app.agent.state import ResearchState
from app.ai.context_builder import build_context
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.default import get_default_agent_gateway

_SURVEY_ANALYZE_PROMPT = (
    "Bạn là chuyên gia nghiên cứu khoa học cao cấp. Dựa trên các tài liệu và evidence trong context, "
    "hãy phân tích học thuật chuyên sâu để chuẩn bị cho một bài báo tổng quan (Literature Survey) xuất sắc theo chuẩn IMRaD:\n"
    "1. Đặt vấn đề & Động lực (Introduction): bối cảnh, khoảng trống tri thức, và phân loại hệ thống.\n"
    "2. Khung phân loại học thuật (Taxonomy & Categorization): phân tích đa chiều các trường phái tiếp cận kỹ thuật.\n"
    "3. Ma trận thực nghiệm định lượng (Empirical Benchmark Matrix): trích xuất các bảng so sánh cụ thể về datasets, metrics, kết quả định lượng giữa các phương pháp.\n"
    "4. Phân tích cơ chế kỹ thuật & Đánh đổi (Technical Mechanisms & Trade-offs): so sánh chi tiết ưu/nhược điểm, độ phức tạp tính toán.\n"
    "5. Thảo luận & Hướng mở (Discussion & Open Challenges): các bài toán chưa được giải quyết, giới hạn của hiện trạng.\n\n"
    "QUY TẮC BẮT BUỘC:\n"
    "- Trích dẫn mỗi luận điểm kế thừa bằng ký hiệu [n] khớp đúng với context.\n"
    "- TUYỆT ĐỐI KHÔNG dùng các nhãn giữ chỗ như [CẦN THÊM NGUỒN], [TODO], [TBD], [Trống]. Mọi nhận định chưa đủ dữ liệu định lượng phải được diễn đạt học thuật dưới dạng thảo luận định tính hoặc đặt ra như câu hỏi nghiên cứu mở."
)

_NOVEL_ANALYZE_PROMPT = (
    "Bạn là nhà khoa học máy tính và AI researcher độc lập xuất sắc. Dựa trên các công trình và evidence trong context, "
    "hãy thực hiện phân tích và phát triển một bài báo khoa học cải tiến / phương pháp mới hoàn chỉnh (Original Novel Research Paper):\n"
    "1. Phân tích Baseline & Điểm nghẽn (Baseline Analysis & Failure Modes): phân tích kỹ lưỡng điểm yếu, sự hạn chế và thất bại của các phương pháp hiện hành trong context [n].\n"
    "2. Đề xuất Phương pháp / Kiến trúc mới (Proposed Methodology): đặt tên cụ thể cho phương pháp/mô hình mới (Acronym), thiết lập bài toán và công thức toán học chính xác (Mathematical Formulation), mô tả nguyên lý hoạt động của từng thành phần.\n"
    "3. Thuật toán & Sơ đồ hệ thống: cung cấp giả mã thuật toán từng bước (Algorithm Pseudocode) và gợi ý cấu trúc sơ đồ Mermaid trực quan.\n"
    "4. Phương án Thực nghiệm & Ma trận Benchmark (Experimental Benchmark Protocol): thiết kế quy trình kiểm thử với các dataset chuẩn, thang đo định lượng và ma trận kết quả thực nghiệm mô phỏng/kỳ vọng so sánh trực diện với baselines.\n"
    "5. Phân tích thực nghiệm bóc tách (Ablation Studies), độ phức tạp tính toán và thảo luận hạn chế.\n\n"
    "CÁC QUY TẮC BẮT BUỘC ĐỂ ĐẠT CHUẨN XUẤT BẢN QUỐC TẾ:\n"
    "- KHÔNG GÁN ÉP TRÍCH DẪN (Anti Force-Mapping): Chỉ được viết 'Tên_phương_pháp [n]' khi bài báo [n] trong context THỰC SỰ là bài báo gốc hoặc đề cập trực tiếp đến phương pháp đó. Không được cite bài HippoRAG cho IRCoT, không cite bài survey cho CoVe nếu bài survey đó không phải là bài đề xuất CoVe. Nếu context chưa có bài báo gốc, hãy ghi rõ 'Tên phương pháp (được khảo sát trong [n])' hoặc chỉ trích dẫn nội dung có thật trong context.\n"
    "- KHIÊM TỐN HỌC THUẬT (Anti-Hype Policy): Tuyệt đối KHÔNG tự xưng là 'first framework', 'mechanistic guarantee', 'proves that error is bounded' khi chưa có chứng minh định lý toán học hoàn chỉnh. Hãy dùng văn phong học thuật: 'we propose a conceptual framework', 'we hypothesize that...', 'our formulation aims to bound error'.\n"
    "- NHẤT QUÁN TOÁN HỌC & KIẾN TRÚC MÔ HÌNH: Mọi ký hiệu đưa vào công thức (như Faith, K_opt) BẮT BUỘC phải được định nghĩa rõ ràng ngay dưới công thức. Dùng ký hiệu phân biệt: R_ret cho Retriever, R cho Reward, Y cho Answer space, t cho hop index. Mô hình Encoder-only (như DeBERTa) chỉ dùng cho tác vụ chấm điểm/phân loại, KHÔNG dùng để sinh/sửa văn bản (REWRITE).\n"
    "- TÍNH TRUNG THỰC VỀ THỰC NGHIỆM: Nếu chưa chạy thực nghiệm (Registered Report), bảng kết quả để '*Not Exp.*', tuyệt đối không tự điền các ước lượng số liệu giả định (như ~2.5 hay ~8) vào cùng bảng gây mâu thuẫn.\n"
    "- TUYỆT ĐỐI KHÔNG dùng các nhãn giữ chỗ như [CẦN THÊM NGUỒN], [TODO], [TBD], [Trống]."
)


def analyze_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    context_text, citations = build_context(state.get("evidence", []))
    mode = state.get("research_mode", "survey")

    system_prompt = _NOVEL_ANALYZE_PROMPT if mode == "novel_research" else _SURVEY_ANALYZE_PROMPT

    mode_label = "Phát triển công trình nghiên cứu cải tiến (Novel Research Paper)" if mode == "novel_research" else "Tổng quan nghiên cứu chuyên sâu (Academic Literature Survey)"
    user_content = (
        f"Chế độ nghiên cứu: {mode_label}\n"
        f"Câu hỏi nghiên cứu: {state['question']}\n\n"
        f"Context tài liệu đã thu thập:\n{context_text}"
    )
    feedback = state.get("critique_feedback")
    if feedback:
        user_content += f"\n\nPhản biện từ lần đánh giá trước, hãy hiệu chỉnh lại: {feedback}"

    gateway, model_name = get_default_agent_gateway(llm)
    response = gateway.generate(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ],
        model_name=model_name,
    )

    clean_draft = sanitize_academic_markdown(response.text)
    return {**state, "draft": clean_draft, "citations": citations}
