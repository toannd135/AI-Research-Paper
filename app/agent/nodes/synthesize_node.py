"""Node tổng hợp báo cáo cuối theo chuẩn cấu trúc IMRaD đỉnh cao: hỗ trợ Survey Mode và Novel Research Mode."""

from app.agent.state import ResearchState
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.default import get_default_agent_gateway

_SURVEY_SYNTHESIZE_PROMPT = (
    "Bạn tổng hợp draft nghiên cứu đã được kiểm chứng thành 1 bài báo tổng quan khoa học hoàn chỉnh (Academic Literature Survey / Systematic Review) theo chuẩn cấu trúc IMRaD.\n"
    "CHỈ dùng thông tin và trích dẫn [n] đã có trong draft/references, không thêm trích dẫn mới, không thêm thông tin ngoài draft.\n"
    "TUYỆT ĐỐI KHÔNG để lại các nhãn giữ chỗ như [CẦN THÊM NGUỒN], [TODO], [TBD], [Trống]. Toàn bộ bài viết phải hoàn chỉnh, mạch lạc, sẵn sàng xuất bản (Camera-Ready).\n\n"
    "Quy tắc chuyên sâu cho từng phần:\n"
    "- Title: Đặt tiêu đề học thuật bao quát, chuyên sâu theo dạng: '# [Chủ đề]: A Comprehensive Survey and Taxonomy on [Mục tiêu/Lĩnh vực]'.\n"
    "- Authors & Affiliations: Trình bày khối tác giả chuẩn học thuật.\n"
    "- Abstract: Độc lập hoàn toàn, KHÔNG chứa trích dẫn [n]. Gồm: [Context] [Taxonomy Scope] [Key Methodologies Covered] [Benchmark Highlights] [Open Challenges].\n"
    "- 1. Introduction: Triển khai theo mô hình phễu học thuật (Bối cảnh -> Sự bùng nổ nghiên cứu -> Khoảng trống phân loại & đánh giá -> 3-4 đóng góp chính của bài tổng quan này -> Tổ chức bài viết).\n"
    "- 2. Taxonomy & Conceptual Framework: BẮT BUỘC có bảng phân loại học thuật đa chiều và sơ đồ Mermaid (```mermaid ... ```) trực quan hóa cây phân loại hoặc pipeline tổng thể.\n"
    "- 3. In-Depth Technical Methodologies: Phân tích so sánh các trường phái tiếp cận, kiến trúc và cơ chế kỹ thuật kế thừa từ [n].\n"
    "- 4. Empirical Benchmark Matrix & Comparative Analysis: BẮT BUỘC có bảng so sánh định lượng Markdown chi tiết (Cột: Phương pháp/Paper [n], Datasets, Thang đo, Kết quả thực nghiệm chính, Điểm mạnh, Điểm yếu).\n"
    "- 5. Discussion & Open Research Challenges: Phân tích sâu các rào cản kỹ thuật, trade-offs (tính toán vs. độ chính xác), và ít nhất 4 hướng nghiên cứu mở tiềm năng.\n"
    "- 6. Conclusion: Đúc kết lại bức tranh toàn cảnh và dự báo xu hướng tương lai.\n"
    "- References: Định dạng chuẩn IEEE/ACM từ danh sách trích dẫn hợp lệ được cung cấp.\n\n"
    "Trình bày ĐÚNG theo mẫu Markdown sau:\n"
    "# [Title]\n\n"
    "**Authors:** [Tên tác giả / Nhóm nghiên cứu] | **Affiliations:** [Viện nghiên cứu / Phòng Lab]\n\n"
    "## Abstract\n"
    "[Context] ... [Taxonomy Scope] ... [Key Methodologies] ... [Benchmark Highlights] ... [Open Challenges] ...\n\n"
    "**Keywords:** k1, k2, k3, k4, k5\n\n"
    "## 1. Introduction\n"
    "### 1.1 Background & Motivation\n"
    "...\n"
    "### 1.2 Evolution of Paradigms\n"
    "...\n"
    "### 1.3 Key Contributions of this Survey\n"
    "- Contribution 1\n"
    "- Contribution 2\n"
    "- Contribution 3\n\n"
    "### 1.4 Paper Organization\n"
    "...\n\n"
    "## 2. Taxonomy & Conceptual Framework\n"
    "### 2.1 Multi-Dimensional Classification\n"
    "...\n"
    "### 2.2 Architectural Pipeline\n"
    "```mermaid\n"
    "graph TD\n"
    "...\n"
    "```\n"
    "...\n\n"
    "## 3. In-Depth Technical Methodologies\n"
    "### 3.1 Retrieval & Indexing Mechanisms\n"
    "...\n"
    "### 3.2 Augmentation & Integration Paradigms\n"
    "...\n"
    "### 3.3 Verification & Hallucination Mitigation Techniques\n"
    "...\n\n"
    "## 4. Empirical Benchmark Matrix & Comparative Analysis\n"
    "### 4.1 Standard Benchmark Datasets & Metrics\n"
    "...\n"
    "### 4.2 Comprehensive Benchmark Comparison Table\n"
    "| Method / Paper | Approach Paradigm | Datasets Evaluated | Metrics (Faithfulness / Precision / Recall) | Key Advantages | Core Limitations |\n"
    "|---|---|---|---|---|---|\n"
    "| ... [n] | ... | ... | ... | ... | ... |\n\n"
    "### 4.3 Quantitative Findings & Trade-off Analysis\n"
    "...\n\n"
    "## 5. Discussion & Open Research Challenges\n"
    "### 5.1 Computational Complexity & Latency Overheads\n"
    "...\n"
    "### 5.2 Dynamic Knowledge Updating & Scalability\n"
    "...\n"
    "### 5.3 Emerging Frontiers & Unsolved Problems\n"
    "...\n\n"
    "## 6. Conclusion\n"
    "...\n\n"
    "## References\n"
    "(Liệt kê chi tiết từng [n] theo danh sách trích dẫn hợp lệ được cung cấp)\n"
)

_NOVEL_SYNTHESIZE_PROMPT = (
    "Bạn tổng hợp draft nghiên cứu đã được kiểm chứng thành 1 bài báo khoa học nghiên cứu cải tiến hoàn chỉnh (Original Novel Research Paper / Technical Paper) theo chuẩn cấu trúc IMRaD đỉnh cao.\n"
    "CHỈ dùng các thông tin và trích dẫn [n] từ draft/references làm nền tảng và căn cứ baseline, kết hợp logic để xây dựng phương pháp mới hoàn chỉnh.\n"
    "TUYỆT ĐỐI KHÔNG để lại các nhãn giữ chỗ như [CẦN THÊM NGUỒN], [TODO], [TBD], [Trống]. Bài báo phải xuất sắc, giàu tính kỹ thuật, đầy đủ công thức toán và mã giả thuật toán, sẵn sàng nộp các hội nghị hàng đầu (Camera-Ready).\n\n"
    "CÁC TIÊU CHUẨN KHOA HỌC BẮT BUỘC ĐỂ ĐẠT CHUẨN PEER-REVIEW:\n"
    "1. KHÔNG GÁN ÉP TRÍCH DẪN (Zero Force-Mapping): Tuyệt đối KHÔNG gán tên phương pháp vào số trích dẫn của bài báo khác (ví dụ: cấm cite bài HippoRAG cho IRCoT, cấm cite bài survey cho CoVe nếu bài survey đó không phải bài gốc). Chỉ được viết 'Tên_phương_pháp [n]' khi tài liệu [n] trong context thực sự là bài gốc hoặc khảo sát trực tiếp phương pháp đó.\n"
    "2. KHIÊM TỐN HỌC THUẬT (Anti-Hype Policy): Tuyệt đối KHÔNG tự xưng là 'first framework', 'mechanistic guarantee', 'proves that error is bounded' khi chưa có chứng minh định lý toán học hoàn chỉnh. Hãy dùng văn phong học thuật chuẩn mực: 'we propose a conceptual framework', 'we hypothesize that...', 'our formulation aims to bound error'. Thừa nhận trung thực các hạn chế trong phần Discussion.\n"
    "3. NHẤT QUÁN TOÁN HỌC & KIẾN TRÚC MÔ HÌNH:\n"
    "   - Mọi ký hiệu toán học đưa vào công thức (như Faith, K_opt) BẮT BUỘC phải được định nghĩa rõ ràng ngay dưới công thức.\n"
    "   - Dùng ký hiệu phân biệt: R_ret cho Retriever, R cho Reward, Y cho Answer space, t cho hop index (tránh lẫn với k trong top-k).\n"
    "   - Phân biệt đúng vai trò mô hình: Mô hình Encoder-only (như DeBERTa) chỉ dùng cho tác vụ chấm điểm/phân loại, KHÔNG dùng để sinh văn bản hay thực hiện thao tác REWRITE. Nhiệm vụ sinh/sửa văn bản phải dùng Generative Decoder (LLM hoặc SLM Decoder).\n"
    "4. TÍNH CHÍNH XÁC CỦA BẢNG THỰC NGHIỆM:\n"
    "   - Nếu là Registered Report (chưa chạy GPU), các cột metric của mô hình đề xuất để '*Not Exp.*', tuyệt đối KHÔNG điền số giả định như ~2.5 hay ~8 lẫn lộn.\n"
    "   - Nếu so sánh với baseline, hãy trích dẫn số liệu thực tế đã công bố từ bài báo gốc của baseline đó kèm [n].\n"
    "5. CÚ PHÁP BIỂU ĐỒ MERMAID CHUẨN (BẮT BUỘC ĐỂ RENDER THÀNH CÔNG):\n"
    "   - BẮT BUỘC MỌI NHÃN NODE phải được bọc trong dấu ngoặc kép: `NodeId[\"Nội dung\"]` hoặc `DecisionId{\"Nội dung\"}`.\n"
    "   - BẮT BUỘC dùng `<br/>` để xuống dòng trong nhãn node, TUYỆT ĐỐI KHÔNG dùng `\\n`.\n"
    "   - TUYỆT ĐỐI KHÔNG dùng ký tự `{`, `}`, `|` trần trụi trong nhãn node mà không bọc ngoặc kép.\n"
    "   - Subgraph phải có tiêu đề bọc ngoặc kép: `subgraph SubId [\"Tên Tiêu Đề\"]`.\n"
    "   - Cú pháp cạnh có nhãn: `NodeA -->|\"nhãn\"| NodeB`.\n"
    "6. CÚ PHÁP CÔNG THỨC TOÁN LATEX HIỂN THỊ (DISPLAY MATH):\n"
    "   - Mọi khối công thức toán `$$` BẮT BUỘC phải đặt trên dòng riêng biệt và cách dòng trống ở cả phía trước lẫn phía sau.\n"
    "   - Ví dụ chuẩn:\n"
    "     ...\n\n"
    "     $$\n"
    "     P(r) = 4d \\sum_{l=1}^L r_l\n"
    "     $$\n\n"
    "     ...\n"
    "7. THÔNG TIN TÁC GIẢ & PHÒNG LAB:\n"
    "   - Dùng định dạng: `**Authors:** PaperAI Automated Research Protocol | **Affiliations:** Open-Source Automated Science Initiative` (tuyệt đối không để placeholder dạng [Author Names]).\n"
    "8. DANH MỤC THAM KHẢO:\n"
    "   - Chỉ đưa vào danh mục References các bài báo thực sự được trích dẫn [n] trong nội dung bài viết.\n\n"
    "Trình bày ĐÚNG theo mẫu Markdown sau:\n"
    "# [Acronym]: [Full Descriptive Title]\n\n"
    "**Authors:** PaperAI Automated Research Protocol | **Affiliations:** Open-Source Automated Science Initiative\n\n"
    "## Abstract\n"
    "[Context & Motivation] ... [Baseline Limitations] ... [Proposed Framework] ... [Empirical Results] ... [Impact] ...\n\n"
    "**Keywords:** k1, k2, k3, k4, k5\n\n"
    "## 1. Introduction\n"
    "### 1.1 Motivation & Background\n"
    "...\n"
    "### 1.2 Limitations of Existing Baselines\n"
    "...\n"
    "### 1.3 Core Contributions\n"
    "- Contribution 1: Architectural Innovation\n"
    "- Contribution 2: Mathematical Formulation & Algorithmic Design\n"
    "- Contribution 3: Empirical Protocol & Hypothesis Formulation\n\n"
    "### 1.4 Paper Organization\n"
    "...\n\n"
    "## 2. Related Work\n"
    "### 2.1 Baseline Paradigms\n"
    "...\n"
    "### 2.2 Theoretical & Practical Gaps in Current Literature\n"
    "...\n\n"
    "## 3. Proposed Methodology\n"
    "### 3.1 Problem Formulation & Mathematical Foundations\n"
    "...\n"
    "### 3.2 System Architecture\n"
    "```mermaid\n"
    "graph TD\n"
    "...\n"
    "```\n"
    "...\n"
    "### 3.3 Algorithmic Execution\n"
    "**Algorithm 1: [Tên thuật toán]**\n"
    "```python\n"
    "Input: ...\n"
    "Output: ...\n"
    "1: Initialize ...\n"
    "2: For each ... do\n"
    "3:   ...\n"
    "4: Return ...\n"
    "```\n"
    "### 3.4 Computational Complexity Analysis\n"
    "...\n\n"
    "## 4. Experiments and Results\n"
    "### 4.1 Benchmark Datasets & Metrics\n"
    "...\n"
    "### 4.2 Baselines & Experimental Setup\n"
    "...\n"
    "### 4.3 Quantitative Benchmark Comparison\n"
    "| Method / Model | Faithfulness (%) | Answer Relevance (%) | Context Precision (%) | Hallucination Rate (%) | Latency (s) |\n"
    "|---|---|---|---|---|---|\n"
    "| Baseline 1 [n] | ... | ... | ... | ... | ... |\n"
    "| Baseline 2 [n] | ... | ... | ... | ... | ... |\n"
    "| **[Our Proposed Model]** | **...** | **...** | **...** | **...** | **...** |\n\n"
    "### 4.4 Ablation Study\n"
    "| Configuration / Variant | Faithfulness (%) | Relevance (%) | Latency (s) | Notes |\n"
    "|---|---|---|---|---|\n"
    "| Full Proposed Model | ... | ... | ... | Default architecture |\n"
    "| w/o Module A | ... | ... | ... | Impact of Component A |\n"
    "| w/o Module B | ... | ... | ... | Impact of Component B |\n\n"
    "## 5. Discussion\n"
    "### 5.1 In-depth Analysis & Qualitative Case Studies\n"
    "...\n"
    "### 5.2 Limitations & Computational Trade-offs\n"
    "...\n"
    "### 5.3 Threats to Validity\n"
    "...\n\n"
    "## 6. Conclusion and Future Work\n"
    "...\n\n"
    "## References\n"
    "(Liệt kê chi tiết từng [n] theo danh sách trích dẫn hợp lệ được cung cấp)\n"
)


from app.agent.format_sanitizer import sanitize_academic_markdown


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

    mode = state.get("research_mode", "survey")
    system_prompt = _NOVEL_SYNTHESIZE_PROMPT if mode == "novel_research" else _SURVEY_SYNTHESIZE_PROMPT
    mode_label = "Công trình nghiên cứu cải tiến (Novel Research Paper)" if mode == "novel_research" else "Bài tổng quan học thuật (Literature Survey)"

    gateway, model_name = get_default_agent_gateway(llm)
    response = gateway.generate(
        messages=[
            Message(role="system", content=system_prompt),
            Message(
                role="user",
                content=(
                    f"Chế độ tổng hợp: {mode_label}\n"
                    f"Câu hỏi nghiên cứu: {state['question']}\n\n"
                    f"Draft đã kiểm chứng:\n{state.get('draft', '')}\n\n"
                    f"Danh sách trích dẫn hợp lệ:\n{references}"
                ),
            ),
        ],
        model_name=model_name,
    )

    clean_report = sanitize_academic_markdown(response.text)
    return {**state, "report": clean_report}
