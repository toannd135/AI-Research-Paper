"""Kiểm tra số lượng hình/bảng theo loại paper (benchmark biên tập nội bộ, KHÔNG phải chuẩn Q1–Q4 hay của nhà xuất bản).

Chỉ tạo cảnh báo (WARNING), không chặn xuất bản và không bao giờ sinh thêm hình/bảng để cho đủ số.
"""

from __future__ import annotations

import re
from typing import Any

# (tối thiểu, tối đa) theo loại paper; đổi ở đây, không hard-code theo quartile.
DISPLAY_TARGETS: dict[str, dict[str, tuple[int, int]]] = {
    "review": {"figures": (5, 9), "tables": (3, 6)},
    "original_research": {"figures": (4, 7), "tables": (3, 5)},
    "system_paper": {"figures": (5, 9), "tables": (3, 5)},
}
_DEFAULT_TARGET = DISPLAY_TARGETS["original_research"]

_FENCE_RE = re.compile(r"```(mermaid|chart|image|table)[ \t]*\n(.*?)```", re.DOTALL)
_MD_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_REF_RE = {
    "figures": re.compile(r"\b(?:Figure|Fig\.)\s*(\d+)", re.I),
    "tables": re.compile(r"\bTable\s*(\d+)", re.I),
}


def _count_markdown_tables(text: str) -> int:
    lines = _FENCE_RE.sub("", text).splitlines()
    return sum(1 for i in range(1, len(lines)) if _MD_TABLE_SEP_RE.match(lines[i]) and lines[i - 1].lstrip().startswith("|"))


_FIG_CAPTION_RE = re.compile(r"^\*\*(?:Figure|Fig\.)\s+\d+[:.]\s*(.*?)\*{0,2}\s*$", re.IGNORECASE | re.MULTILINE)
_GENERIC_CAPTIONS = ("qualitative visual comparison", "visual comparison", "qualitative comparison", "qualitative results", "experimental results", "results")
_LICENSE_RE = re.compile(r"reproduc|licen[cs]e|permission|adapted from|courtesy", re.IGNORECASE)
MIN_CAPTION_WORDS = 6


def check_figure_captions(text: str) -> list[str]:
    """Caption chung chung/trùng nhau; ảnh lấy từ paper gốc thiếu nguồn [n] hoặc ghi chú tái sử dụng (cảnh báo, không chặn)."""
    warnings: list[str] = []
    seen: dict[str, int] = {}
    for m in _FIG_CAPTION_RE.finditer(_FENCE_RE.sub("", text)):
        cap = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".")
        norm = re.sub(r"\[\d+\]|[^a-z ]", "", cap.lower()).strip()
        seen[norm] = seen.get(norm, 0) + 1
        if norm in _GENERIC_CAPTIONS or len(norm.split()) < MIN_CAPTION_WORDS:
            warnings.append(f"caption hình chung chung/quá ngắn: '{cap[:80]}' (cần nêu phương pháp, dataset, ý nghĩa panel)")
    warnings += [f"caption hình trùng nhau: '{c[:60]}'" for c, n in seen.items() if n > 1 and c]
    for fence in _FENCE_RE.finditer(text):
        if fence.group(1) != "image":
            continue
        cap = re.search(r'"caption"\s*:\s*"(.*?)"', fence.group(2), re.DOTALL)
        caption = cap.group(1) if cap else ""
        if not re.search(r"\[\d+\]", caption) or not _LICENSE_RE.search(caption):
            warnings.append(f"ảnh lấy từ paper gốc thiếu nguồn [n] hoặc ghi chú tái sử dụng/giấy phép trong caption: '{caption[:60]}'")
    return warnings


def check_display_items(text: str, paper_type: str | None) -> dict[str, Any]:
    """Đếm hình (mermaid/chart/image) và bảng (khối table + bảng Markdown), đối chiếu với lời nhắc 'Figure N'/'Table N'."""
    target = DISPLAY_TARGETS.get(paper_type or "", _DEFAULT_TARGET)
    kinds = [m.group(1) for m in _FENCE_RE.finditer(text)]
    counts = {
        "figures": sum(k in ("mermaid", "chart", "image") for k in kinds),
        "tables": kinds.count("table") + _count_markdown_tables(text),
    }
    body = _FENCE_RE.sub("", text)
    warnings: list[str] = []
    for key, label in (("figures", "Figure"), ("tables", "Table")):
        lo, hi = target[key]
        n = counts[key]
        if n < lo:
            warnings.append(f"{label}: có {n}, thấp hơn mục tiêu {lo}–{hi} (không bịa thêm để cho đủ số)")
        elif n > hi:
            warnings.append(f"{label}: có {n}, vượt mục tiêu {lo}–{hi}")
        mentioned = {int(x) for x in _REF_RE[key].findall(body)}
        dangling = sorted(x for x in mentioned if x > n)
        if dangling:
            warnings.append(f"{label} {dangling} được nhắc trong thân bài nhưng không có khối tương ứng")
        if n and len(mentioned) < n:
            warnings.append(f"{label}: {n} khối nhưng chỉ {len(mentioned)} số được nhắc trong thân bài")
    warnings += check_figure_captions(text)
    chart_types = []
    for m in _FENCE_RE.finditer(text):
        if m.group(1) == "chart":
            t = re.search(r'"type"\s*:\s*"(\w+)"', m.group(2))
            chart_types.append(t.group(1) if t else "bar")
    return {"counts": counts, "target": target, "chart_types": chart_types, "warnings": warnings}
