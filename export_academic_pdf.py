"""Export Academic Research Paper to Publication-Ready PDF (Typst Engine).

Converts result.json / academic markdown into IEEE / CVPR style 2-column PDF.
Usage:
    python export_academic_pdf.py
    python export_academic_pdf.py --input result.json --output literature_review.pdf
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from app.agent.format_sanitizer import sanitize_academic_markdown
from app.pipeline.export.typst_renderer import render_report_to_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("export_academic_pdf")


def export_pdf(input_path: str = "result.json", output_path: str = "literature_review.pdf") -> str:
    in_file = Path(input_path)
    if not in_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    logger.info(f"Loading input file: {in_file}")
    if in_file.suffix == ".json":
        with open(in_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw_report = data.get("report", "")
        citations = data.get("citations", [])
    else:
        raw_report = in_file.read_text(encoding="utf-8")
        citations = []

    logger.info("Sanitizing academic markdown syntax...")
    clean_report = sanitize_academic_markdown(raw_report)

    logger.info("Compiling with Typst Academic Engine (CVPR / IEEE Two-Column)...")
    out_file = Path(output_path)
    pdf_bytes = render_report_to_pdf(
        report_md=clean_report,
        citations=citations,
        output_pdf_path=out_file,
    )

    logger.info(f"Successfully generated publication PDF: {out_file} ({len(pdf_bytes):,} bytes)")
    return str(out_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile Academic Markdown / result.json to Typst PDF")
    parser.add_argument("--input", "-i", default="result.json", help="Path to input JSON or Markdown file")
    parser.add_argument("--output", "-o", default="literature_review.pdf", help="Path to output PDF file")
    args = parser.parse_args()

    export_pdf(args.input, args.output)
