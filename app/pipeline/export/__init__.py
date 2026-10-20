"""Xuất report Markdown của ResearchTask ra PDF dạng bài báo khoa học.

Hỗ trợ 2 engine:
1. Playwright Chromium HTML2PDF — mặc định cho endpoint PDF.
2. Typst Academic Engine — bản hai cột tùy chọn.
"""

try:
    from app.pipeline.export.typst_renderer import markdown_to_typst, render_report_to_pdf
except ImportError:
    markdown_to_typst = None
    render_report_to_pdf = None

__all__ = ["render_report_to_pdf", "markdown_to_typst"]
