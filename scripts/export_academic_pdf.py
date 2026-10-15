"""Xuất báo cáo nghiên cứu (result.json hoặc file Markdown) ra PDF 2 cột chuẩn hội nghị bằng Typst.

Cách dùng (chạy từ thư mục gốc repo):
    python scripts/export_academic_pdf.py
    python scripts/export_academic_pdf.py --input docs/samples/result.json --output out/literature_review.pdf
    python scripts/export_academic_pdf.py --input report.md --markdown out/clean.md   # xuất kèm Markdown đã chuẩn hoá

Input JSON cần có khoá "report" (markdown) và tuỳ chọn "citations" (list dict).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agent.format_sanitizer import sanitize_academic_markdown  # noqa: E402
from app.pipeline.export.typst_renderer import render_report_to_pdf  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("export_academic_pdf")


def export_pdf(input_path: str, output_path: str, markdown_path: str | None = None) -> str:
    in_file = Path(input_path)
    if not in_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file input: {input_path}")

    logger.info("Đọc input: %s", in_file)
    if in_file.suffix == ".json":
        data = json.loads(in_file.read_text(encoding="utf-8"))
        raw_report = data.get("report", "")
        citations = data.get("citations", [])
    else:
        raw_report = in_file.read_text(encoding="utf-8")
        citations = []

    clean_report = sanitize_academic_markdown(raw_report)
    if markdown_path:
        md_out = Path(markdown_path)
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(clean_report, encoding="utf-8")
        logger.info("Đã ghi Markdown chuẩn hoá: %s", md_out)

    out_file = Path(output_path)
    pdf_bytes = render_report_to_pdf(report_md=clean_report, citations=citations, output_pdf_path=out_file)
    logger.info("Đã tạo PDF: %s (%s bytes)", out_file, f"{len(pdf_bytes):,}")
    return str(out_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Biên dịch Markdown học thuật / result.json ra PDF Typst")
    parser.add_argument("--input", "-i", default="docs/samples/result.json", help="File JSON hoặc Markdown đầu vào")
    parser.add_argument("--output", "-o", default="out/literature_review.pdf", help="File PDF đầu ra")
    parser.add_argument("--markdown", "-m", default=None, help="(Tuỳ chọn) ghi thêm Markdown đã chuẩn hoá ra file này")
    args = parser.parse_args()
    export_pdf(args.input, args.output, args.markdown)
