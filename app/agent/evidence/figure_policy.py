"""Chart Selection Policy: mỗi hình trả lời một câu hỏi riêng, không mặc định biểu đồ cột (không LLM).

- `refine_chart_spec`: đổi loại hình theo câu hỏi mà dữ liệu trả lời — hai điều kiện ghép cặp (validation/test,
  có/không module, full/thiếu modality) → dumbbell (thấy ngay khoảng chênh); nhiều phương pháp × nhiều metric → dot plot.
  Chỉ đổi cách vẽ, không đổi số.
- `figure_policy_warnings`: cảnh báo quá nhiều biểu đồ cột, hai hình cùng dữ liệu, hình chỉ lặp lại một bảng.
"""

from __future__ import annotations

import json
import re
from typing import Any

BAR_TYPES = {"bar", "barh"}
MAX_BAR_CHARTS = 2
_PAIRED_RE = [
    (re.compile(r"\bval(?:idation)?\b", re.I), re.compile(r"\btest(?:ing)?\b", re.I)),
    (re.compile(r"\btrain(?:ing)?\b", re.I), re.compile(r"\btest(?:ing)?\b|\bval(?:idation)?\b", re.I)),
    (re.compile(r"\binternal\b", re.I), re.compile(r"\bexternal\b", re.I)),
    (
        re.compile(r"\bwith(?!out)\b|^\s*(?:full|ours|proposed)\b", re.I),
        re.compile(r"\bwithout\b|\bw/o\b|\bno\s|\bbaseline\b", re.I),
    ),
    (
        re.compile(r"\bfull\b|\bcomplete\b|\ball modalit", re.I),
        re.compile(r"\bmissing\b|\bincomplete\b|\bpartial\b", re.I),
    ),
    (re.compile(r"\bbefore\b|\bpre\b", re.I), re.compile(r"\bafter\b|\bpost\b", re.I)),
]
_FENCE_RE = re.compile(r"```(chart|table)[ \t]*\n(.*?)```", re.DOTALL)
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _is_paired(a: str, b: str) -> bool:
    return any((x.search(a) and y.search(b)) or (x.search(b) and y.search(a)) for x, y in _PAIRED_RE)


def _horizontal(spec: dict[str, Any], kind: str) -> dict[str, Any]:
    """dot/dumbbell vẽ giá trị trên trục NGANG: bar dọc mang tên metric ở y_label thì chuyển sang x_label."""
    out = {**spec, "type": kind}
    if spec.get("type", "bar") == "bar" and spec.get("y_label"):
        out["x_label"] = out.pop("y_label")
    return out


def refine_chart_spec(spec: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Trả (spec mới, lý do đổi) — lý do None nếu giữ nguyên. Không động tới biểu đồ đã được chỉ định loại khác bar."""
    kind = spec.get("type", "bar")
    series = [s for s in spec.get("series") or [] if isinstance(s, dict)]
    labels = spec.get("labels") or []
    if kind not in BAR_TYPES or not series or not labels or any(s.get("errors") for s in series):
        return spec, None  # error bar là thông tin riêng của biểu đồ cột → giữ
    if len(series) == 2 and _is_paired(str(series[0].get("name") or ""), str(series[1].get("name") or "")):
        return _horizontal(spec, "dumbbell"), "hai điều kiện ghép cặp → dumbbell"
    if len(series) >= 3 or (len(series) == 2 and len(labels) >= 4):
        return _horizontal(spec, "dot"), "nhiều phương pháp × metric → dot plot"
    return spec, None


def _numbers(obj: Any) -> list[float]:
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        return [float(x) for x in _NUM_RE.findall(obj)]
    if isinstance(obj, list):
        return [v for x in obj for v in _numbers(x)]
    if isinstance(obj, dict):
        return [v for x in obj.values() for v in _numbers(x)]
    return []


def _chart_values(spec: dict[str, Any]) -> list[float]:
    if "matrix" in spec:
        return _numbers(spec["matrix"])
    return [
        v
        for s in spec.get("series") or []
        if isinstance(s, dict)
        for k in ("values", "y", "samples")
        for v in _numbers(s.get(k))
    ]


def figure_policy_warnings(text: str) -> list[str]:
    charts: list[dict[str, Any]] = []
    table_values: list[set[float]] = []
    for kind, body in _FENCE_RE.findall(text):
        try:
            spec = json.loads(body)
        except ValueError:
            continue
        if not isinstance(spec, dict):
            continue
        if kind == "chart":
            charts.append(spec)
        else:
            table_values.append(set(_numbers(spec.get("rows"))))
    warnings: list[str] = []
    bars = sum(c.get("type", "bar") in BAR_TYPES for c in charts)
    if bars > MAX_BAR_CHARTS:
        warnings.append(
            f"hình: {bars} biểu đồ cột (tối đa {MAX_BAR_CHARTS}) — chọn loại hình theo câu hỏi (dot/dumbbell/heatmap/evidence map)"
        )
    seen: list[tuple[int, set[float]]] = []
    for i, spec in enumerate(charts, start=1):
        values = set(_chart_values(spec))
        if len(values) < 4:
            continue
        for j, other in seen:
            if len(values & other) >= 0.8 * min(len(values), len(other)):
                warnings.append(f"hình: biểu đồ thứ {i} vẽ lại cùng dữ liệu với biểu đồ thứ {j} — giữ một hình")
                break
        seen.append((i, values))
        if not spec.get("derived") and any(values <= t for t in table_values):
            warnings.append(
                f"hình: biểu đồ thứ {i} chỉ lặp lại số của một bảng — bỏ hoặc thay bằng hình cho góc nhìn mới"
            )
    return warnings
