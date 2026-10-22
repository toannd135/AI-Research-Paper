"""Chuẩn hoá một báo cáo đã sinh (result.json hoặc .md): làm sạch format, gộp reference trùng, dịch mọi chỗ lẫn ngôn ngữ về --lang.

Dùng cho báo cáo cũ; báo cáo mới đã qua các bước này trong pipeline. Dịch cần gọi LLM (theo .env).

    python scripts/normalize_report.py docs/samples/result.json out.md --lang en
"""

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agent.format_sanitizer import sanitize_academic_markdown  # noqa: E402
from app.agent.report_postprocess import translate_foreign_paragraphs  # noqa: E402
from app.ai.llm_gateway.default import get_default_agent_gateway  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()

    src = Path(args.input)
    raw = json.loads(src.read_text(encoding="utf-8"))["report"] if src.suffix == ".json" else src.read_text(encoding="utf-8")
    gateway, model = get_default_agent_gateway()
    report = sanitize_academic_markdown(translate_foreign_paragraphs(sanitize_academic_markdown(raw), args.lang, gateway, model))
    Path(args.output).write_text(report, encoding="utf-8")
    logging.info("Đã ghi %s (%d ký tự)", args.output, len(report))


if __name__ == "__main__":
    main()
