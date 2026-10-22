# Kế hoạch: Paper đa đối tượng, đa lĩnh vực

## 1. Tóm tắt hiện trạng
- Pipeline: clarify → plan → search (Qdrant nội bộ + OpenAlex) → analyze (draft + Quantitative Evidence Ledger) → synthesize (Stage 0–6) → postprocess → Typst PDF.
- Kiểm soát bịa số đã khá tốt: ledger ở analyze_node.py:10, `scrub_table_spec`/`scrub_chart_spec` xoá ô không có trong draft (report_postprocess.py:116,144).
- **Không có ảnh thật nào trong toàn bộ pipeline**: parser chỉ lấy text, renderer chỉ biết chart/mermaid/table.
- **Không có tham số đối tượng (audience) hay lĩnh vực (field)** ở API, DB, state hay prompt.
- Prompt và cấu trúc các mục mặc định là CS/ML (benchmark, ablation, "AI researcher"). Bộ lọc miền còn **chặn thẳng** các đề tài môi trường, nông nghiệp và y tế.
- Nguồn ngoài chỉ có abstract OpenAlex, nên số liệu cho lĩnh vực ngoài CS rất mỏng và biểu đồ thường rỗng.

## 2. Bảng audit
| Trục | Hiện trạng (file:line) | Thiếu | Tác động |
|---|---|---|---|
| Ảnh thật | pdf_parser.py:19 chỉ `page.get_text("text")`; typst_renderer.py:538-562 chỉ có chart/mermaid; Chunk (schemas.py:45) không có trường ảnh | Không trích figure từ PDF, không có khối `image`, không lưu nguồn/giấy phép | Paper xử lý ảnh không có ảnh minh hoạ trước/sau; paper môi trường không có ảnh hiện trường |
| Số liệu/biểu đồ | Ledger analyze_node.py:10-16; chart chỉ bar/barh/line/stacked (pdf_renderer.py:73); auto chart chèn trước "## 5." (report_postprocess.py:264-269) | Không có nguồn dữ liệu mở (World Bank, OWID…), không trích bảng số từ PDF, không có scatter/box/map/time-series có trục thời gian | Biểu đồ chỉ có khi abstract chứa số; đề tài môi trường/kinh tế gần như không có biểu đồ |
| Lĩnh vực | search_node.py:21-27 danh sách đen "wildfire, crop yield, agricultural, solar cell, dermatology…"; dataset_catalog.py:11 chỉ có LLM-judge; _NOVEL_ANALYZE_PROMPT analyze_node.py:33 "nhà khoa học máy tính và AI researcher"; _STAGE_STRUCTURES synthesize_node.py:98-190 cố định "Benchmark Matrix", "Ablation" | Không có profile lĩnh vực (mục bắt buộc, metric chuẩn, kiểu hình) | Đề tài ngoài CS bị lọc mất evidence và bị ép vào khung ML |
| Đối tượng | ResearchRequest schemas.py:234 chỉ có question + clarification_answers; ResearchTask không có cột audience; run_graph graph.py:54 chỉ question/language; clarify.py:7 hỏi "mục đích" nhưng chỉ gộp vào refined_question | Không truyền audience vào state/prompt/template; một giọng "top-tier peer-reviewed" cho mọi người (synthesize_node.py:349,373…) | Sinh viên và người đi làm nhận bài quá hàn lâm, thiếu tóm tắt điều hành, thuật ngữ, ví dụ |
| So sánh/thảo luận | stage4/stage5 synthesize_node.py:120-187 có bảng so sánh, trade-off, limitations | Không có bảng ưu/nhược theo tiêu chí thực tiễn (chi phí, triển khai); chú thích mermaid cứng "System Architectural and Evaluation Pipeline Overview" (typst_renderer.py:561) | Thảo luận thiên học thuật; chú thích hình sai ngữ cảnh |

## 3. Danh sách cải tiến
| ID | Hạng mục | Ưu tiên | Tệp ảnh hưởng | Công | Phụ thuộc |
|---|---|---|---|---|---|
| A1 | Thay danh sách đen miền cứng bằng lọc theo field profile (hoặc bỏ) | P0 | search_node.py | S | F1 |
| F1 | Field profile: cv, environment, medicine, economics, education, cs-general (mục bắt buộc, metric chuẩn, kiểu hình/biểu đồ gợi ý) | P0 | mới app/agent/profiles.py, plan_node.py, synthesize_node.py | M | – |
| U1 | Audience profile: lecturer / student / professional → giọng văn, độ dài, mục thêm | P0 | profiles.py, schemas.py:234, graph.py:54, tasks.py, synthesize_node.py, analyze_node.py | M | – |
| I1 | Trích figure + caption từ PDF đã upload (pymupdf `get_images` + dò "Fig./Hình" gần ảnh), lưu file và metadata nguồn | P0 | pdf_parser.py, pipeline/tasks.py, bảng mới `paper_figures` | L | duyệt schema DB |
| I2 | Khối ```image {"ref": "...", "caption", "source", "license"} trong markdown → Typst `#figure(image())` kèm dòng nguồn | P0 | typst_renderer.py, pdf_renderer.py (HTML), report_postprocess.py (kiểm ref hợp lệ) | M | I1 |
| C1 | Sửa chú thích mermaid lấy từ dòng "**Figure N:**" do LLM viết | P0 | typst_renderer.py:555-562 | S | – |
| D1 | Connector dữ liệu mở (World Bank / OWID) cho chủ đề kinh tế, môi trường; số đưa vào ledger với nguồn [n] riêng | P1 | mới app/ai/external/open_data.py, analyze_node.py | L | F1, duyệt nguồn |
| D2 | Thêm loại chart: scatter, grouped line theo năm, box | P1 | pdf_renderer.py:50-156 | M | – |
| I3 | Ảnh minh hoạ ngoài có giấy phép (Wikimedia Commons / Openverse) khi không có figure trong PDF | P1 | mới app/ai/external/images.py | M | I2, duyệt API |
| T1 | Trích bảng số từ PDF (pymupdf `find_tables`) vào ledger | P1 | pdf_parser.py, chunking | M | – |
| U2 | Template Typst theo đối tượng (bìa/tóm tắt điều hành cho người đi làm, glossary box cho sinh viên) | P2 | templates/*.typ | M | U1 |
| M1 | Bản đồ (choropleth) cho dữ liệu theo vùng | P2 | pdf_renderer.py | L | D1 |

## 4. Thiết kế kỹ thuật cho các mục P0
**F1 + U1 (profile)**
- `app/agent/profiles.py`: `FIELD_PROFILES: dict[str, FieldProfile]` (keywords, required_sections, metrics, figure_hints, off_domain=[]) và `AUDIENCE_PROFILES: dict[str, AudienceProfile]` (register, word_scale, extra_sections, glossary: bool).
- Luồng dữ liệu: `ResearchRequest.audience: Literal["lecturer","student","professional"] = "lecturer"` (+ `field: str | None`) → `create_research` (research.py:68) → task → `run_graph(..., audience, field)` (graph.py:51) → `ResearchState.audience/field` (state.py:8).
- Nếu `field` không được truyền: plan_node suy ra lĩnh vực (LLM trả kèm field cùng search_queries; fallback dùng keyword).
- Prompt: `_global_standards` (synthesize_node.py:55) thêm khối "AUDIENCE & FIELD ADAPTATION" sinh từ profile. Mục bắt buộc của field được nối vào `_structure()` (synthesize_node.py:193); thay câu "AI researcher" (analyze_node.py:33) bằng vai trò theo field.
- Ví dụ field cv: bắt buộc "Qualitative Results" với ảnh input/output, metric PSNR/SSIM/mAP/IoU. Ví dụ field environment: chuỗi thời gian, so sánh theo vùng, ảnh hiện trường, đơn vị đo chuẩn.
- Đối tượng: **student** thêm Glossary, "Key takeaways", ví dụ trực quan và hạ mức toán. **professional** thêm Executive Summary đầu bài và bảng "Ứng dụng – Chi phí – Rủi ro – Mức sẵn sàng". **lecturer** giữ như hiện tại, nhấn phương pháp luận và threats to validity.

**A1**: `is_domain_relevant` (search_node.py:13) chỉ áp `off_domain` của field profile hiện tại (mặc định rỗng), không còn danh sách cứng.

**I1 + I2 (ảnh thật)**
- Khi ingest (tasks.py `process_paper`), trích ảnh ≥ 200×200 px, ghép caption theo vị trí bbox và lưu `uploads/figures/{paper_id}/{n}.png`.
- Bảng `paper_figures(id, paper_id, page, caption, path, width, height)` cần **migration**, phải duyệt trước. Phương án không cần migration: JSON sidecar cạnh file PDF.
- Caption được embed như một chunk loại `figure` để retrieve cùng evidence. Evidence có `figure_id` → `_format_references_prompt` liệt kê "Available figures: [F3] caption (from [n], p.5)".
- LLM chỉ được dùng ```image {"ref":"F3", ...}; postprocess bỏ mọi ref không có trong danh sách. Renderer chèn hình và chú thích "Nguồn: [n], trang p".

**C1**: lấy caption từ dòng `**Figure N: ...**` ngay trên khối mermaid; nếu không có thì để chú thích trống thay vì câu cứng.

## 5. Cơ chế toàn vẹn dữ liệu
- Mỗi ảnh có `source` (paper_id + trang, hoặc URL), `license`, `author`; ảnh ngoài chỉ nhận giấy phép CC0/CC-BY/CC-BY-SA/PD. Thiếu giấy phép thì không dùng.
- Mỗi số trong table/chart phải nằm trong ledger (đã có, report_postprocess.py:116-150). Số từ dữ liệu mở vào ledger kèm dataset id + năm truy xuất.
- Không có dữ liệu thì bỏ hình hoặc biểu đồ, không vẽ minh hoạ giả. Sơ đồ khái niệm (mermaid) ghi rõ "Sơ đồ minh hoạ khái niệm".
- Không dùng ảnh AI sinh ra làm "ảnh thật".

## 6. Kế hoạch test
- Unit (app/agent/tests):
  - `test_profiles.py`: mỗi field/audience có đủ khóa; `_global_standards` chứa khối audience đúng.
  - `test_search_node.py`: đề tài môi trường giữ được chunk "wildfire".
  - `test_typst_renderer.py`: khối image hợp lệ → `#figure(image(...))` kèm nguồn; ref lạ bị bỏ; caption mermaid lấy từ dòng Figure.
  - `test_report_postprocess.py`: image ref không tồn tại bị xoá.
  - `test_pdf_parser.py`: PDF mẫu có 1 hình trả 1 figure kèm caption.
- API: `ResearchRequest` thiếu audience → mặc định lecturer; giá trị lạ → 422.
- Acceptance (thủ công, LLM thật): 2 đề tài ("khử nhiễu ảnh y tế bằng diffusion" – cv; "ô nhiễm PM2.5 tại Hà Nội 2015–2024" – environment) × 3 đối tượng = 6 PDF. Đạt khi:
  - bài cv có ≥1 hình qualitative lấy từ PDF upload, kèm nguồn;
  - bài môi trường có ≥1 biểu đồ chuỗi thời gian với số trong ledger;
  - bài student có Glossary, bài professional có Executive Summary;
  - không có số nào ngoài ledger (script kiểm).
- Hồi quy: `pytest app/agent/tests -q`.

## 7. Rủi ro và quyết định chờ người dùng
- Rủi ro bản quyền figure từ PDF upload: chỉ dùng cho người upload và luôn ghi nguồn; cần chính sách nếu chia sẻ công khai.
- Trích ảnh từ PDF dễ ra logo/ảnh vụn → lọc theo kích thước và bắt buộc có caption.
- Prompt dài thêm làm tăng token và model free (OpenRouter) dễ bỏ qua quy tắc → chỉ chèn phần profile liên quan.
- Field profile có thể suy sai → cho phép người dùng chọn ở clarify/frontend.
- **Quyết định cần chốt:**
  1. Nguồn ảnh ngoài: Wikimedia Commons, Openverse, hay chỉ dùng figure từ PDF upload (P0 chỉ cần PDF).
  2. Lưu `audience`/`field`: thêm cột vào `research_tasks` (cần migration) hay chỉ giữ trong request/state (không lưu lại được).
  3. Lưu figure: bảng `paper_figures` (migration) hay JSON sidecar.
  4. Nguồn dữ liệu mở chấp nhận cho P1: World Bank, OWID, và/hoặc nguồn Việt Nam (GSO).
