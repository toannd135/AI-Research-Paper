"""Chạy lại các bước sửa tất định (không gọi LLM) trên báo cáo ĐÃ LƯU của một research task rồi xuất Markdown + PDF.

Dùng cho báo cáo sinh trước khi có các bản sửa trong `evidence/repair.py` / `report_structure.py` / `citation_cleaner.py`.
Không ghi DB: chỉ ghi file ra --out-dir.

    source scripts/host_env.sh
    python scripts/repair_task_report.py 5a736250 --suffix test5

Các bước:
1. Cụm trích dẫn trong khối hình (mermaid/chart) còn chỉ số THÔ (bản cũ không đánh số lại cụm trong fence) → ánh xạ
   chỉ số thô → số reference cuối theo tiêu đề (`--legacy-fence-remap`, mặc định bật).
2. Gỡ điểm chart UNTRACED theo bản ghi truy vết trong `validation/<task>.json`.
3. Paper trong kho chưa được cite → đoạn "Additional corpus studies" + thêm mục References.
4. Dựng lại References từ catalog (metadata đã sửa), dọn trích dẫn treo, sửa chart trộn vùng, câu ledger, hạ giọng Abstract/Conclusion,
   đánh số lại mục/bảng/hình, viết lại "Paper Organization", bỏ tham chiếu bản nháp nội bộ.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agent.evidence.citation_cleaner import (  # noqa: E402
    _extract_citation_metadata,
    _local_catalog,
    _normalize_title,
    collapse_duplicate_citations,
)
from app.agent.evidence.repair import (  # noqa: E402
    add_uncited_corpus,
    drop_duplicate_charts,
    redact_untraced_chart_points,
    repair_chart_regions,
    repair_ledger_claims,
    soften_promotional_claims,
)
from app.agent.evidence.report_structure import (  # noqa: E402
    _FENCE_RE,
    _LOCATED_CITE_RE,
    _MERMAID_CITE_RE,
    _clean_data_fence,
    finalize_structure_report,
    strip_dangling_citations,
)
from app.agent.format_sanitizer import sanitize_academic_markdown  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("repair_task_report")

_REF_LINE_RE = re.compile(r'^\[(\d+)\]\s+(.*?),\s*"(.*?),?"', re.M)
_CLUSTER_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)+)\]")


def load_task(prefix: str) -> tuple[str, str, list[dict]]:
    from sqlalchemy import create_engine, text

    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        row = conn.execute(
            text("select id, report, citations from research_tasks where id like :p"), {"p": f"{prefix}%"}
        ).one()
    return row.id, row.report, json.loads(row.citations or "[]")


def _meta(c: dict) -> dict:
    return _extract_citation_metadata(c.get("paper_id", ""), str(c.get("text_snippet", "")))


def raw_to_final(report: str, citations: list[dict]) -> dict[int, int]:
    """Chỉ số thô (thứ tự trong state.citations) → số reference cuối, khớp theo tiêu đề chuẩn hoá."""
    refs = report.split("\n## References", 1)[1] if "\n## References" in report else ""
    final = {_normalize_title(m.group(3)): int(m.group(1)) for m in _REF_LINE_RE.finditer(refs)}
    out: dict[int, int] = {}
    for i, c in enumerate(citations, start=1):
        n = final.get(_normalize_title(_meta(c)["title"]))
        if n:
            out[i] = n
    return out


def remap_legacy_fence_clusters(report: str, mapping: dict[int, int], n_refs: int) -> tuple[str, int]:
    """Bản cũ: số đơn trong fence đã được đánh số lại, cụm '[a,b]' và '[n, Table k]' có số > n_refs thì chưa → đổi theo `mapping`."""
    changed = 0

    def _cluster(m: re.Match) -> str:
        nonlocal changed
        nums = [int(x) for x in re.findall(r"\d+", m.group(0))]
        if len(nums) < 2:
            return m.group(0)
        changed += 1
        new = [mapping[n] for n in nums if n in mapping]
        return "[" + ", ".join(str(n) for n in dict.fromkeys(new)) + "]" if new else ""

    def _located(m: re.Match) -> str:
        nonlocal changed
        nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
        if all(n <= n_refs for n in nums):
            return m.group(0)
        changed += 1
        new = [mapping[n] for n in nums if n in mapping]
        return "[" + ", ".join(map(str, dict.fromkeys(new))) + ", " + m.group(2) + "]" if new else ""

    def _json(v):
        if isinstance(v, str):
            return _CLUSTER_RE.sub(_cluster, _LOCATED_CITE_RE.sub(_located, v))
        if isinstance(v, list):
            return [_json(x) for x in v]
        if isinstance(v, dict):
            return {k: _json(x) for k, x in v.items()}
        return v

    def _fence(m: re.Match) -> str:
        block = m.group(0)
        if block.startswith("```mermaid"):
            return _MERMAID_CITE_RE.sub(_cluster, block)
        if block.startswith(("```chart", "```table")):
            return _clean_data_fence(block, _json)
        return block

    return _FENCE_RE.sub(_fence, report), changed


def ordered_citations(report: str, citations: list[dict]) -> list[dict]:
    """Danh sách citation theo số reference cuối 1..N, rồi các paper trong kho chưa cite (mỗi paper một lần)."""
    mapping = raw_to_final(report, citations)
    by_final: dict[int, dict] = {}
    for raw, n in mapping.items():
        by_final.setdefault(n, citations[raw - 1])
    ordered = [by_final[n] for n in sorted(by_final)]
    seen = {c["paper_id"] for c in ordered}
    for c in citations:
        if c["paper_id"] not in seen:
            seen.add(c["paper_id"])
            ordered.append(c)
    return ordered


def format_references(cits: list[dict]) -> list[str]:
    lines = []
    for i, c in enumerate(cits, start=1):
        m = _meta(c)
        doi = f", DOI: {m['doi']}" if m["doi"] else ""
        lines.append(f"[{i}] {m['authors']}, \"{m['title']},\" *{m['venue']}*, {m['year']}{doi}.")
    return lines


def repair(report: str, citations: list[dict], untraced: list[dict], legacy: bool = True) -> str:
    n_refs = len(_REF_LINE_RE.findall(report.split("\n## References", 1)[-1]))
    text = report
    if legacy:
        text, n = remap_legacy_fence_clusters(text, raw_to_final(report, citations), n_refs)
        logger.info("Đổi %d cụm trích dẫn chỉ số thô trong khối hình", n)
    # gỡ điểm UNTRACED trước khi sửa chart khác (số thứ tự khối chart#k phải khớp bản gate đã chấm)
    text, removed = redact_untraced_chart_points(text, untraced)
    logger.info("Gỡ %d điểm chart không truy vết được", len(removed))

    cits = ordered_citations(report, citations)
    head = text.split("\n## References", 1)[0]
    objs = [SimpleNamespace(**c) for c in cits]
    head, added = add_uncited_corpus(head, objs, _local_catalog())
    if added:
        logger.info("Bổ sung %d paper chưa cite", len(added))
    refs = format_references(cits[: n_refs + len(added)])
    text = head.rstrip() + "\n\n## References\n\n" + "\n\n".join(refs) + "\n"
    text = collapse_duplicate_citations(text)

    text, dangling = strip_dangling_citations(text, len(refs))
    if dangling:
        logger.info("Xoá trích dẫn treo: %s", sorted(set(dangling)))
    text, _ = repair_chart_regions(text)
    text, _ = drop_duplicate_charts(text)
    text, _ = repair_ledger_claims(text, 0)
    text, _ = soften_promotional_claims(text)
    text, dangling_refs, low_conf = finalize_structure_report(text)
    if dangling_refs or low_conf:
        logger.warning("Còn tham chiếu treo %s / gán theo vị trí %s", dangling_refs, low_conf)
    return sanitize_academic_markdown(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_prefix")
    ap.add_argument("--suffix", default="repaired")
    ap.add_argument("--out-dir", default=str(ROOT / "data" / "exports"))
    ap.add_argument("--no-legacy-fence-remap", action="store_true")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()

    task_id, report, citations = load_task(args.task_prefix)
    vpath = Path(os.environ.get("UPLOAD_DIR", "data/papers_brain")) / "validation" / f"{task_id}.json"
    untraced = json.loads(vpath.read_text())["traceability"].get("untraced", []) if vpath.exists() else []
    fixed = repair(report, citations, untraced, legacy=not args.no_legacy_fence_remap)

    out = Path(args.out_dir)
    stem = f"paper_{task_id[:8]}_{args.suffix}"
    (out / f"{stem}.md").write_text(fixed, encoding="utf-8")
    logger.info("Ghi %s", out / f"{stem}.md")
    if not args.no_pdf:
        from app.pipeline.export.pdf_renderer import report_to_pdf

        (out / f"{stem}.pdf").write_bytes(report_to_pdf(fixed, columns=2))
        logger.info("Ghi %s", out / f"{stem}.pdf")


if __name__ == "__main__":
    main()
