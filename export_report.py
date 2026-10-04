import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from app.agent.format_sanitizer import sanitize_academic_markdown
from app.pipeline.export.typst_renderer import render_report_to_pdf

# 1. Đọc dữ liệu báo cáo từ result.json
with open("result.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# 2. Tự động chuẩn hóa toàn diện cú pháp Mermaid, LaTeX math, code blocks trước khi xuất
report_content = sanitize_academic_markdown(data["report"])
citations = data.get("citations", [])

# 3. Xuất ra file markdown
md_path = "literature_review.md"
with open(md_path, "w", encoding="utf-8") as file:
    file.write(report_content)
print(f"1. Đã xuất Markdown thành công ra file: {md_path}")

# 4. Xuất ra PDF chuẩn học thuật 2 cột bằng Typst Academic Engine (Phương án 3)
pdf_path = "literature_review.pdf"
pdf_bytes = render_report_to_pdf(
    report_md=report_content,
    citations=citations,
    output_pdf_path=pdf_path,
)
print(f"2. Đã xuất PDF 2 cột chuẩn hội nghị (CVPR/IEEE) thành công ra file: {pdf_path} ({len(pdf_bytes):,} bytes)")