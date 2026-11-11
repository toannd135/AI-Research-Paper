# Bàn giao: xuất PDF chuẩn LaTeX (2026-11-11)

## Đã làm
- `GET /research/{id}/pdf` mặc định `engine=latex`: `compile_latex_pdf` (latex_renderer.py) sinh IEEEtran rồi biên dịch bằng Tectonic (XeTeX + BibTeX). Lỗi → lùi về HTML/Chromium.
- latex_renderer: font TeX Gyre Termes khi XeTeX (pdflatex vẫn dùng inputenc/fontenc); tham số float giảm khoảng trắng;
  bảng tabularx (cột chữ dài tự xuống dòng), `table*` khi ≥4 cột hoặc chữ dài, bảng dài cắt thành "(continued)";
  biểu đồ/sơ đồ rộng → `figure*` (dùng chart_span/mermaid_span); Mermaid → PDF vector qua Chromium (`mermaid_to_pdf`),
  co theo cỡ chữ tự nhiên (`_diagram_scale`); nhận caption "**Figure N: tiêu đề.** mô tả"; danh sách đánh số cách dòng trống không reset.
- Dockerfile cài Tectonic 0.15.0 + biên dịch thử để cache gói. Frontend `researchPdfUrl` mặc định `latex`.
- Test: test_latex_renderer.py (4 test mới), test_research_route.py (latex mặc định + fallback).

## Kết quả
- paper_5a736250_test5: 22 trang HTML → 16 trang LaTeX, không còn trang hở nửa trang (`data/exports/paper_5a736250_test5_latex.pdf`).

## Đang chờ
- Docker compose chỉ có redis/postgres/qdrant; api/worker chạy trên máy (Tectonic ở ~/.local/bin). Dockerfile đã có Tectonic cho khi đóng gói.
- Frontend: đã commit 4332f84 (nhánh feature/normalization, chưa push).
- (Đã sửa) nhãn năm chart timeline: `_spaced_years` giãn theo bề rộng trục, tên nhóm xuống dòng.
- Lint cũ chưa sửa ở research.py/pdf_renderer.py/typst_renderer.py (không thuộc thay đổi này).
