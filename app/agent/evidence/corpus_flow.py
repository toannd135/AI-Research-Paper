"""Sơ đồ hình thành corpus TRUNG THỰC khi không có `review_protocol.json` (không phải PRISMA).

Số trên sơ đồ lấy từ chính lần chạy (paper trong phạm vi, paper có đoạn được truy xuất, paper được trích dẫn, paper có kết quả
định lượng kiểm chứng nguyên văn) — không có bước sàng lọc độc lập nào được giả định. Không gọi LLM.
"""

from __future__ import annotations

import re
from itertools import pairwise

CORPUS_FLOW_MARK = "Cited in this review (n ="  # nhãn ngắn: sơ đồ ngang trải trang, chữ trong hộp đủ lớn khi in
_LEGACY_MARK = "Papers cited in this review (n ="  # nhãn cũ, để bài đã sinh trước đó không bị chèn sơ đồ lần hai


def corpus_flow_block(corpus_size: int | None, retrieved: int, cited: int, with_results: int) -> str | None:
    """Khối chú thích + mermaid; None nếu số đếm không nhất quán (không vẽ luồng sai)."""
    if cited < 1 or retrieved < cited:
        return None
    nodes = []
    if corpus_size and corpus_size >= retrieved:
        nodes.append(f'A["PDFs in the review corpus (n = {corpus_size})"]')
    nodes.append(f'B["Retrieved for the research questions (n = {retrieved})"]')
    nodes.append(f'C["{CORPUS_FLOW_MARK} {cited})"]')
    edges = [f"  {a.split('[')[0]} --> {b.split('[')[0]}" for a, b in pairwise(nodes)]
    lines = [f"  {n}" for n in nodes] + edges
    if 0 < with_results <= cited:
        lines += [f'  D["With verbatim-verified results (n = {with_results})"]', "  C --> D"]
    caption = (
        "**Figure 1: Corpus formation flow of this corpus-based narrative review.** Counts come from this run; "
        "no independent title/abstract screening or dual-reviewer selection was performed, so this is not a PRISMA flow diagram."
    )
    # vẽ ngang: 3–4 hộp thành một dải thấp trải cả trang thay vì một cột cao gần nửa trang
    # dàn dọc (TD): 4 hộp dàn ngang rộng ~1100pt, thu vào trang chữ chỉ còn ~5.6pt; dọc thì vừa một cột, chữ ~8pt
    return caption + "\n\n```mermaid\nflowchart TD\n" + "\n".join(lines) + "\n```"


def inject_corpus_flow(report: str, block: str | None) -> str:
    """Chèn trước mục 2.3 (hoặc trước mục 3) như sơ đồ PRISMA; đã có PRISMA/sơ đồ corpus thì giữ nguyên."""
    if not block or "Records identified (n =" in report or CORPUS_FLOW_MARK in report or _LEGACY_MARK in report:
        return report
    marker = re.search(r"^###\s*2\.3\b", report, re.M) or re.search(r"^##\s*3\.", report, re.M)
    if not marker:
        return report
    return report[: marker.start()] + block + "\n\n" + report[marker.start() :]
