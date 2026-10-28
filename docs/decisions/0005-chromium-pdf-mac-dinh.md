# 0005 — Xuất PDF mặc định bằng Chromium (HTML), Typst là tùy chọn
Trạng thái: accepted
**Bối cảnh:** cần 2 cột, bảng/hình trải ngang, Mermaid + KaTeX offline.
**Quyết định:** `engine=html` (Playwright Chromium, tài nguyên đóng gói sẵn trong Docker) là mặc định; `engine=typst` và LaTeX/BibTeX còn hỗ trợ.
**Hệ quả:** chạy ngoài Docker phải cài Chromium + `npm ci` ở `app/pipeline/export/assets`; lỗi toán của LLM xử lý riêng cho Typst (`_compile_with_math_repair`).
