"""Phase 4 — phân tích định lượng suy ra từ `ResultRecord` (không từ LLM): Δ so với tốt nhất, Δ ablation, đánh đổi Dice–Params.

Chỉ sinh khối khi đủ điều kiện (≥3 phương pháp CÙNG dataset/version/split/vùng/metric/đơn vị); số suy ra được gắn
`"derived": true` để traceability/scrub không coi là số trích từ PDF. Không bao giờ tạo số giả để lấp biểu đồ.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.evidence.quant_check import ResultRecord, group_comparable
from app.agent.evidence.stats import lower_is_better

MIN_METHODS = 3
MAX_GROUPS = 3
MAX_ROWS = 8


def _key(rec: ResultRecord) -> tuple:
    return (rec.paper_id, rec.model, rec.dataset, rec.dataset_version, rec.split, rec.region, rec.metric, rec.unit)


def _setting(rec: ResultRecord) -> str:
    return " ".join(x for x in (rec.dataset, rec.dataset_version, rec.split and f"({rec.split})") if x)


def _block(kind: str, spec: dict[str, Any]) -> str:
    return f"```{kind}\n{json.dumps(spec, ensure_ascii=False)}\n```"


def delta_table(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str | None:
    """Bảng Δ so với giá trị tốt nhất trong từng nhóm COMPARABLE (HD95 thấp hơn là tốt hơn); đơn vị Δ = đơn vị gốc."""
    main = [r for r in records if not r.variant and r.paper_id in paper_to_n]
    groups = group_comparable(main)["groups"]
    eligible = []
    for items in groups.values():
        best_per_model: dict[str, ResultRecord] = {}
        for r in items:
            best_per_model.setdefault(r.model or r.paper_id, r)
        if len(best_per_model) >= MIN_METHODS:
            eligible.append(list(best_per_model.values()))
    eligible.sort(key=len, reverse=True)
    rows: list[list[str]] = []
    for items in eligible[:MAX_GROUPS]:
        sample = items[0]
        low = lower_is_better(sample.metric)
        best = (min if low else max)(r.value for r in items)
        for r in sorted(items, key=lambda r: r.value if low else -r.value)[:MAX_ROWS]:
            rows.append([
                f"{r.model} [{paper_to_n[r.paper_id]}]", _setting(r), f"{sample.metric} {sample.region}", f"{r.value:g}", f"{r.value - best:+.2f}",
            ])
    if not rows:
        return None
    caption = "Gap to the best reported value within each directly comparable setting (derived from the cited values; unit as in the sources)"
    return _block("table", {"caption": caption, "columns": ["Method [Ref]", "Setting", "Metric", "Value", "Δ vs best"], "rows": rows, "derived": True})


def ablation_table(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str | None:
    """Δ(biến thể − mô hình đầy đủ) khi cùng paper, model, dataset/version/split, vùng, metric, đơn vị."""
    full = {_key(r): r for r in records if not r.variant}
    rows: list[list[str]] = []
    for r in records:
        base = full.get(_key(r)) if r.variant else None
        if base is None or r.paper_id not in paper_to_n:
            continue
        rows.append([f"{r.model} [{paper_to_n[r.paper_id]}]", r.variant or "", f"{r.metric} {r.region or ''}".strip(), f"{base.value:g}", f"{r.value:g}", f"{r.value - base.value:+.2f}"])
    if not rows:
        return None
    return _block("table", {"caption": "Ablation: variant versus the full model as reported in each source", "columns": ["Method [Ref]", "Variant", "Metric", "Full", "Variant value", "Δ"], "rows": rows[:MAX_ROWS * 2], "derived": True})


def tradeoff_scatter(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str | None:
    """Scatter Dice (một vùng, một setting) theo Params; mỗi điểm một phương pháp, đơn vị Params phải giống nhau."""
    params = {(r.paper_id, r.model): r for r in records if r.metric.lower() in ("params", "parameters") and not r.variant}
    by_setting: dict[tuple, list[tuple[ResultRecord, ResultRecord]]] = {}
    for r in records:
        p = params.get((r.paper_id, r.model))
        if r.metric.lower() != "dice" or r.variant or p is None or r.paper_id not in paper_to_n:
            continue
        if None in (r.dataset, r.dataset_version, r.split, r.region) or not r.unit or not p.unit:
            continue
        by_setting.setdefault((r.dataset, r.dataset_version, r.split, r.region, r.unit, p.unit), []).append((r, p))
    best = max(by_setting.items(), key=lambda kv: len(kv[1]), default=None)
    if not best or len({x[0].model for x in best[1]}) < MIN_METHODS:
        return None
    (ds, ver, split, region, unit, p_unit), pairs = best
    seen: dict[str, tuple[ResultRecord, ResultRecord]] = {}
    for d, p in pairs:
        seen.setdefault(d.model, (d, p))
    series = [{"name": f"{m} [{paper_to_n[d.paper_id]}]", "x": [p.value], "y": [d.value]} for m, (d, p) in seen.items()]
    cites = ", ".join(sorted({f"[{paper_to_n[d.paper_id]}]" for d, _ in seen.values()}))
    caption = f"Dice ({region}) versus parameter count on {ds} {ver} ({split}) {cites}"
    return _block("chart", {"type": "scatter", "caption": caption, "x_label": f"Parameters ({p_unit})", "y_label": f"Dice {region} ({unit})", "series": series})


def build_quant_blocks(records: list[ResultRecord], paper_to_n: dict[str, int]) -> list[str]:
    return [b for b in (delta_table(records, paper_to_n), ablation_table(records, paper_to_n), tradeoff_scatter(records, paper_to_n)) if b]


def inject_quant_blocks(report: str, blocks: list[str]) -> str:
    """Chèn các khối trước mục 5.5 (hoặc trước mục 6, hoặc cuối bài) — không tạo mục mới."""
    if not blocks:
        return report
    marker = re.search(r"^###\s*5\.5\b", report, re.M) or re.search(r"^##\s*6\.", report, re.M)
    text = "\n\n".join(blocks) + "\n\n"
    return report[: marker.start()] + text + report[marker.start():] if marker else report.rstrip() + "\n\n" + text
