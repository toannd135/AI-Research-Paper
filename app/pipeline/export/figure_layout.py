"""Figure Layout: quyết định hình nằm trong MỘT cột (mặc định) hay trải cả hai cột của bản PDF hai cột.

Hình chỉ trải hai cột khi cần để đọc được (nhiều nhãn/cột dữ liệu, sơ đồ ngang nhiều nút), không trải chỉ để to hơn:
hình trải hai cột buộc trình duyệt cân bằng cột trước/sau hình và sinh khoảng trắng.
Kích thước vẽ khớp bề rộng thật (Letter, lề 18 mm, khe cột 18 pt) để chữ trong hình in ra ~8–9 pt, không bị thu nhỏ.
"""

from __future__ import annotations

import re

COLUMN = "column"
WIDE = "wide"
COLUMN_WIDTH_IN = 3.4  # bề rộng một cột
WIDE_WIDTH_IN = 6.9  # bề rộng cả trang (hai cột + khe)

_LONG_LABEL = 18  # ký tự; nhãn dài hơn khó xếp trên trục ngang một cột
_MAX_COLUMN_BARS = 12  # số cột/điểm tối đa vẫn đọc được trong một cột
_MAX_COLUMN_MATRIX_COLS = 5  # heatmap/evidence map: số cột tối đa trong một cột


def _labels(spec: dict) -> list[str]:
    return [str(x) for x in spec.get("labels") or []]


def chart_span(spec: dict) -> str:
    """`layout` do người viết chỉ định thì giữ; không thì suy từ lượng nhãn/dữ liệu cần đọc được."""
    layout = spec.get("layout")
    if layout in (COLUMN, WIDE):
        return layout
    kind = spec.get("type", "bar")
    if kind == "panels":  # lưới nhiều ô con luôn chiếm cả trang
        return WIDE
    if kind == "timeline":  # nhiều mốc trên trục năm cần bề ngang để nhãn không chồng
        return WIDE if len(spec.get("events") or []) > 8 else COLUMN
    if kind in ("heatmap", "evidence_map"):
        cols = len(spec.get("x_labels") or [])
        longest = max((len(str(x)) for x in spec.get("x_labels") or []), default=0)
        return WIDE if cols > _MAX_COLUMN_MATRIX_COLS or (cols > 3 and longest > _LONG_LABEL) else COLUMN
    if kind in ("bar", "line", "stacked_bar"):  # nhãn nằm trên trục ngang
        labels = _labels(spec)
        n_series = max(1, len(spec.get("series") or []))
        longest = max((len(x) for x in labels), default=0)
        crowded = len(labels) * n_series > _MAX_COLUMN_BARS or (len(labels) > 4 and longest > _LONG_LABEL)
        return WIDE if crowded else COLUMN
    return COLUMN  # barh, dot, dumbbell, xy, phân phối: nhãn nằm trục dọc, một cột đủ đọc


def chart_width(spec: dict) -> float:
    return WIDE_WIDTH_IN if chart_span(spec) == WIDE else COLUMN_WIDTH_IN


_MERMAID_NODE_RE = re.compile(r"(?<![\w\"])([A-Za-z][\w-]*)\s*[\[({]")


def mermaid_span(code: str) -> str:
    """Sơ đồ ngang (LR/RL) nhiều nút cần cả trang; sơ đồ dọc (TD/TB) hoặc ít nút vừa một cột."""
    horizontal = re.match(r"\s*(?:graph|flowchart)\s+(?:LR|RL)\b", code) is not None
    nodes = len(set(_MERMAID_NODE_RE.findall(code)))
    return WIDE if (horizontal and nodes > 4) or nodes > 12 else COLUMN
