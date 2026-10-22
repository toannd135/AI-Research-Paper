# Cải tiến PaperAI — đã làm, còn thiếu, ý tưởng

Nguồn: so sánh PDF app xuất (`docs/samples/result.json`) với 5 bài mẫu CVPR trong `docs/samples/` (Letter, Times 10pt, 2 cột, 14–18 trang, 42–67 reference, 4–13 hình, có phụ lục, có kết quả thực nghiệm).

## 1. Đã làm

### Biểu đồ chuẩn Q1/Q2 (`pdf_renderer.py`, `chart_scientific.py`)
- `bar` / `barh` / `line` nhận `series[].errors` (SD hoặc CI95) → error bar.
- Type mới: `xyline` (hội tụ, độ nhạy 1D, scalability; có error bar, log scale), `heatmap` (độ nhạy 2D), `scatter` (PCA/t-SNE/UMAP), `histogram`, `boxplot`, `cdf` (có đường P95/P99).
- Prompt (`_CHART_BLOCK_RULE`) hướng dẫn chọn dạng biểu đồ theo loại bằng chứng, giữ quy tắc không bịa số.
- Hàm vẽ nhận `fmt = svg | pdf | eps` (font TrueType nhúng, vector).

### Xuất BibTeX / LaTeX / bảng khảo sát
- `bibliography.py`: `## References` → `references.bib` (cite key `ref{n}` khớp `[n]`), `survey_table_spec` (Ref., Authors, Year, Venue).
- `latex_renderer.py`: gói zip `paper.tex` + `references.bib` + `figures/` (biểu đồ PDF/EPS riêng). Template `ieee` (IEEEtran) và `cvpr` (cần `cvpr.sty` của hội nghị), `\cite{}`, booktabs, `\appendix`.
- Route: `GET /research/{id}/bib`, `GET /research/{id}/latex?chart_format=pdf|eps&survey_table=true&template=ieee|cvpr`.

### Sửa layout theo bài mẫu
- Khổ Letter, font Times-like (Liberation Serif / Nimbus Roman), thân 10pt, caption 9pt serif, tiêu đề 15pt.
- Tác giả / đơn vị parse được cả dạng `|` lẫn hai dòng riêng; Status gộp thành một dòng chú thích; abstract một cột (kể cả khi có `<hr>`); tiêu đề Typst không justify / hyphenate.
- Công thức có `|` trong hàng bảng → `\vert` (HTML + Typst); header bảng `($ H_0 $) | ($ H_1 $)` không còn bị ghép xuyên ô (chỉ engine HTML).

### Làm sạch dữ liệu / ngôn ngữ
- `sanitize_raw_references`: reference dạng snippet thô → `[n] Authors, "Title," *Venue*, Year.` (thiếu năm → `n.d.`, thiếu tác giả → `Anonymous`, không đoán).
- `dedupe_references`: gộp reference trùng tiêu đề, đánh số lại, cập nhật `[n]` trong thân bài và chuỗi khối table/chart.
- `translate_foreign_paragraphs` dịch cả tiêu đề, bảng Markdown, JSON table/chart, nhãn mermaid (có kiểm tra cấu trúc); bộ nhận diện ngôn ngữ bỏ công thức trước khi xét.
- `scripts/normalize_report.py` chuẩn hoá báo cáo cũ; kết quả mẫu: `docs/samples/result_en.md`.

### Prompt / pipeline
- Title ≤ 15 từ; abstract một đoạn 150–220 từ, không bold sub-label; chỉ `##` và `###`; bỏ "Paper Organization"; cấm dòng Manuscript Type / Protocol Version.
- Thêm `## Appendix A. Implementation and Evaluation Details` (150–400 từ, chỉ dùng dữ kiện có sẵn).
- Truy xuất nguồn: `count_per_query` 8 → 12, `max_total` 30 → 50.

## 2. Còn thiếu / chưa kiểm chứng

| Mục | Ghi chú |
|---|---|
| LaTeX chưa biên dịch thử | Máy không có `pdflatex`; test chỉ kiểm cấu trúc `.tex`. Chạy `pdflatex → bibtex → pdflatex ×2` trên một bản xuất thật. |
| Sơ đồ mermaid trong LaTeX | Chỉ lưu `.mmd` + khung chỗ trống; chưa có bộ đổi sang PDF. |
| Metadata `.bib` | Chỉ có tác giả đầu / et al., tiêu đề, venue, năm, DOI (pipeline chỉ lưu bấy nhiêu). Cần kiểm tra tay trước khi nộp. |
| Prompt mới chưa chạy với LLM | Appendix, title ngắn, abstract một đoạn, bỏ "Paper Organization" chưa được kiểm chứng bằng một bài sinh mới. |
| `result_en.md` mới đọc mẫu | Dịch bằng Groq (OpenRouter hết hạn mức free); chưa đọc lại toàn bộ bài. |
| Hạn mức LLM | Chỉ `GROQ_API_KEY` còn hiệu lực; OpenRouter chạm giới hạn free hằng ngày; Gemini / Anthropic / OpenAI chưa có khoá. |
| Hình thực | Bài chỉ có 4 hình; mẫu có 4–13. Hình phụ thuộc dữ liệu thật, app không tạo hình khi thiếu số liệu. |
| Kết quả thực nghiệm | Bản pre-registration không có số liệu; mọi bài mẫu đều có bảng so sánh SOTA và ablation. Phải chạy thí nghiệm thật. |
| Đo trên Jetson | Không thuộc app; cần chạy trên thiết bị và đưa số liệu vào bài. |
| Số reference | Đã tăng trần truy xuất lên 50 nhưng vẫn có thể thấp hơn 100+ nếu OpenAlex không trả đủ bài liên quan. |

## 3. Ý tưởng cải tiến tiếp

### Chất lượng bài
1. **Thêm bước "Experiments thật"**: nhận bảng kết quả người dùng tải lên (CSV/JSON: method × dataset × metric × runs) rồi tự dựng bảng so sánh có `highlight_best`, biểu đồ có error bar, ablation, độ nhạy — thay vì chỉ dựa trên số trong nguồn.
2. **Literature Survey Table giàu hơn**: trích thêm cột Method / Dataset / Metric / Kết quả chính từ chunk của từng bài (kèm `[n]`), không chỉ metadata.
3. **Giới hạn độ dài theo template**: mục tiêu ~7–8k từ cho 8 trang CVPR/IEEE; sau khi xuất, đo số trang và tự yêu cầu rút gọn nếu vượt.
4. **Kiểm tra trước khi xuất**: lint báo cáo (mục tiếng khác ngôn ngữ, `####`, reference trùng, `[n]` không có trong References, bảng/figure không được nhắc trong văn bản) và trả danh sách cảnh báo kèm file PDF.
5. **Hình minh hoạ tổng quan (teaser / pipeline)** bắt buộc cho bài `novel_research`; ưu tiên hình thật trích từ PDF đã tải (`AVAILABLE FIGURES`).

### Xuất bản
6. **Bộ đổi mermaid → PDF** (Playwright `page.pdf` trên SVG) để LaTeX có hình sơ đồ vector thật.
7. **CI biên dịch LaTeX**: container có `texlive` chạy test biên dịch gói zip cho cả hai template.
8. **Template ACM / Elsevier** và chọn template ở UI (hiện chỉ `ieee`, `cvpr`).
9. **Reference nâng cao**: bổ sung metadata (đủ tác giả, venue, DOI) từ OpenAlex theo `paper_id` thay vì suy ra từ snippet; xuất thêm RIS / CSL-JSON.
10. **Route tải riêng hình**: `GET /research/{id}/figures.zip` (PDF/EPS/PNG) cho tạp chí yêu cầu nộp hình tách file.

### Vận hành
11. **Fallback provider cho bước dịch**: khi 429 thì tự chuyển provider kế tiếp trong `_PROVIDER_ORDER` thay vì bỏ qua đoạn.
12. **Bộ test dữ liệu mẫu**: đưa 1–2 PDF mẫu và `result_en.md` vào test hồi quy hiển thị (đếm cột, khổ giấy, font, số trang) để các thay đổi layout không làm hỏng lặng lẽ.
13. **Chuẩn hoá lúc xuất**: gọi `sanitize_academic_markdown` ở mọi route xuất (đã dùng ở `/pdf`, `/bib`, `/latex`) và thêm tùy chọn `?normalize_language=en` chạy dịch cho báo cáo cũ.

## 4. Template paper theo lĩnh vực

Template do **nơi nộp bài** quy định; bảng dưới là mặc định thường gặp (kiến thức chung, cần đối chiếu author guidelines của đúng tạp chí / hội nghị vì quy định đổi theo năm).

| Lĩnh vực | Template / quy định thường gặp |
|---|---|
| Điện, điện tử, viễn thông, IoT, kỹ thuật | IEEE `IEEEtran` (`conference` / `journal`), 2 cột, tham khảo `[n]` theo thứ tự xuất hiện, Index Terms, hình vector PDF/EPS. |
| Thị giác máy tính | CVPR / ICCV / ECCV: `cvpr.sty`, Letter, 2 cột, Times 10pt, ~8 trang không tính reference, double-blind. |
| Học máy | NeurIPS / ICML / ICLR: style file riêng, 1 cột (NeurIPS, ICLR) hoặc 2 cột (ICML), giới hạn trang cố định, có mục reproducibility / broader impact tuỳ năm. |
| NLP | ACL / EMNLP / NAACL: `acl.sty`, 2 cột, A4, bắt buộc mục Limitations. |
| Khoa học máy tính (ACM) | `acmart` (`sigconf`, `acmsmall`…), bắt buộc CCS Concepts và ACM Reference Format. |
| Elsevier / Springer / Wiley | `elsarticle`, `svjour3` / Springer Nature, `wiley`; thường 1 cột khi nộp; trích dẫn có thể tên tác giả–năm (Harvard). |
| Y sinh, lâm sàng | IMRaD; CONSORT (thử nghiệm lâm sàng), PRISMA (khảo sát hệ thống), STROBE (quan sát) kèm lưu đồ và checklist; trích dẫn Vancouver (số); abstract có cấu trúc. |
| Vật lý, toán | APS `revtex`, AIP, `amsart`; toán nhấn mạnh định lý / chứng minh, không có mục Experiments. |
| Hoá học, vật liệu | ACS, RSC (Word / LaTeX riêng); Supporting Information tách file, dữ liệu thực nghiệm chi tiết. |
| Khoa học xã hội, kinh tế, tâm lý | APA 7 (tác giả–năm), kinh tế có mục Robustness checks. |

### Đề xuất đưa vào app
1. **Chọn nơi nộp bài** (venue) ở UI/API rồi map sang bộ ba: template (`ieee`, `cvpr`, `acl`, `acmart`, `elsarticle`…), kiểu trích dẫn (số / tác giả–năm), cấu trúc mục.
2. **Mở rộng `app/agent/profiles.py`**: mỗi profile lĩnh vực / venue thêm trường `template`, `citation_style`, `page_limit`, `required_sections` (Limitations, Reproducibility, CONSORT / PRISMA flow…), `anonymous` (double-blind: ẩn tác giả và đơn vị).
3. **Kiểu trích dẫn thứ hai**: hiện chỉ có `[n]` → `\cite{}`; thêm tác giả–năm (`\citep` / `\citet`, bst `plainnat` / `apalike`) trong `latex_renderer.py` và trong HTML/Typst.
4. **Cấu trúc IMRaD và checklist** cho profile y sinh: prompt dùng Methods / Results / Discussion, abstract có cấu trúc, mục CONSORT / PRISMA khi phù hợp.
5. **Template mới cho LaTeX**: `acl`, `acmart`, `elsarticle`, `revtex`, `neurips` (người dùng tự đặt file `.sty` / `.cls` cạnh `paper.tex`, như `cvpr` hiện tại).
6. **Kiểm tra theo venue trước khi xuất**: số trang vượt giới hạn, thiếu mục bắt buộc, còn tên tác giả khi cần ẩn danh → trả cảnh báo kèm file.
