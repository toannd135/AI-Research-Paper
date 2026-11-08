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


_MODALITY_CANON = {"t1": "T1", "t1c": "T1c", "t1ce": "T1c", "t1gd": "T1c", "t1-gd": "T1c", "t1+c": "T1c", "t2": "T2", "flair": "FLAIR"}
FULL_MODALITIES = frozenset({"T1", "T1c", "T2", "FLAIR"})
_MODALITY_ORDER = ("T1", "T1c", "T2", "FLAIR")


def _modality_set(rec: ResultRecord) -> frozenset[str]:
    """Tập modality chuẩn hóa của bản ghi; rỗng nếu không có hoặc có tên không nhận ra (không đoán)."""
    mods = {_MODALITY_CANON.get(re.sub(r"[\s_]", "", m.lower())) for m in rec.modality}
    return frozenset(mods) if mods and None not in mods else frozenset()


def _subset_label(mods: frozenset[str]) -> str:
    if mods == FULL_MODALITIES:
        return "Full (T1, T1c, T2, FLAIR)"
    return "+".join(m for m in _MODALITY_ORDER if m in mods)


def _modality_groups(records: list[ResultRecord], paper_to_n: dict[str, int]) -> dict[tuple, dict[frozenset[str], ResultRecord]]:
    """Nhóm theo (paper, model, dataset, version, split, vùng, metric, đơn vị) -> {tập modality: bản ghi}; chỉ giữ nhóm có ≥2 tập."""
    groups: dict[tuple, dict[frozenset[str], ResultRecord]] = {}
    for r in records:
        mods = _modality_set(r)
        if r.variant or not mods or r.paper_id not in paper_to_n:
            continue
        key = (r.paper_id, r.model, r.dataset, r.dataset_version, r.split, r.region, r.metric, r.unit)
        groups.setdefault(key, {}).setdefault(mods, r)
    return {k: v for k, v in groups.items() if len(v) >= 2}


def modality_matrix_stats(records: list[ResultRecord], paper_to_n: dict[str, int]) -> dict[str, int]:
    """Số liệu thật về độ phủ missing-modality, dùng cho EVIDENCE LIMITS và kiểm tra."""
    groups = _modality_groups(records, paper_to_n)
    with_full = sum(1 for g in groups.values() if FULL_MODALITIES in g)
    subsets = {s for g in groups.values() for s in g}
    singles = {next(iter(s)) for s in subsets if len(s) == 1}
    return {"groups": len(groups), "groups_with_full": with_full, "distinct_subsets": len(subsets), "single_modalities": len(singles)}


def missing_modality_table(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str | None:
    """Ma trận kết quả theo tập modality sẵn có; Δ so với full-modality CHỈ khi chính nguồn đó báo kết quả full (ngược lại 'n/r')."""
    groups = _modality_groups(records, paper_to_n)
    if not groups:
        return None
    rows: list[list[str]] = []
    for by_mods in (g for _, g in sorted(groups.items(), key=lambda kv: -len(kv[1]))):
        full = by_mods.get(FULL_MODALITIES)
        sample = next(iter(by_mods.values()))
        for mods, r in sorted(by_mods.items(), key=lambda kv: (-len(kv[0]), _subset_label(kv[0]))):
            delta = "n/r" if full is None else ("0.00" if mods == FULL_MODALITIES else f"{r.value - full.value:+.2f}")
            rows.append([f"{r.model} [{paper_to_n[r.paper_id]}]", _setting(sample), f"{sample.metric} {sample.region or ''}".strip(), _subset_label(mods), f"{r.value:g}", delta])
    caption = "Results by available MRI modalities; Δ is the change from the full-modality result of the same source (n/r = full-modality result not reported in that source)"
    return _block("table", {"caption": caption, "columns": ["Method [Ref]", "Setting", "Metric", "Available modalities", "Value", "Δ vs full"], "rows": rows[: MAX_ROWS * 3], "derived": True})


def modality_degradation_chart(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str | None:
    """Biểu đồ giá trị đã báo cáo theo tập modality sẵn có, trong MỘT setting; chỉ vẽ các tập mà mọi model được vẽ đều có số (không null)."""
    by_setting: dict[tuple, dict[str, dict[frozenset[str], ResultRecord]]] = {}
    for key, by_mods in _modality_groups(records, paper_to_n).items():
        by_setting.setdefault(key[2:], {})[key[0] + "|" + str(key[1])] = by_mods
    best: tuple[list[frozenset[str]], list[dict[frozenset[str], ResultRecord]], tuple] | None = None
    for setting, models in by_setting.items():
        usable = [m for m in models.values() if len(m) >= 3]
        if not usable:
            continue
        common = set.intersection(*(set(m) for m in usable))
        subsets, chosen = (sorted(common, key=lambda x: (-len(x), _subset_label(x))), usable) if len(common) >= 3 else (None, None)
        if subsets is None:
            top = max(usable, key=len)
            subsets, chosen = sorted(top, key=lambda x: (-len(x), _subset_label(x))), [top]
        if best is None or len(subsets) * len(chosen) > len(best[0]) * len(best[1]):
            best = (subsets, chosen, setting)
    if best is None:
        return None
    subsets, chosen, (ds, ver, split, region, metric, unit) = best
    series = []
    for by_mods in chosen:
        first = next(iter(by_mods.values()))
        series.append({"name": f"{first.model} [{paper_to_n[first.paper_id]}]", "values": [by_mods[m].value for m in subsets]})
    cites = ", ".join(sorted({s["name"].rsplit(" ", 1)[1] for s in series}))
    setting_txt = " ".join(x for x in (ds, ver, split and f"({split})") if x)
    caption = f"{metric} {region or ''} on {setting_txt} versus available MRI modalities {cites}".replace("  ", " ")
    return _block("chart", {"type": "bar", "caption": caption, "labels": [_subset_label(m) for m in subsets], "series": series, "y_label": f"{metric} {region or ''} ({unit or 'as reported'})".replace("  ", " ")})


def evidence_limits(records: list[ResultRecord], paper_to_n: dict[str, int], n_papers: int) -> str:
    """Các giới hạn THẬT của số liệu đã trích, để chương Limitations nêu đúng thay vì bịa hoặc bỏ qua."""
    stats = modality_matrix_stats(records, paper_to_n)
    lines = ["EVIDENCE LIMITS (computed from the extracted records; state these plainly in the Limitations and wherever a claim depends on them):"]
    lines.append(f"- {len(records)} verified numeric records were extracted from {n_papers} papers; every value is a single reported point estimate (no standard deviation, confidence interval or significance test was extracted).")
    if stats["groups"] == 0:
        lines.append("- No source in the corpus reports results for subsets of the four modalities in a form that could be extracted, so no per-modality (missing T1/T1c/T2/FLAIR) degradation matrix or ΔDice/ΔHD95 can be built; say this is a limitation and do not infer it.")
    else:
        lines.append(
            f"- Missing-modality results were extracted for {stats['groups']} method/setting groups ({stats['groups_with_full']} also report full-modality results, "
            f"{stats['distinct_subsets']} distinct modality subsets, {stats['single_modalities']} single-modality subsets); the matrix is therefore incomplete and Δ is only given where the same source reports both conditions."
        )
    return "\n".join(lines)


def build_quant_blocks(records: list[ResultRecord], paper_to_n: dict[str, int]) -> list[str]:
    return [
        b
        for b in (
            delta_table(records, paper_to_n),
            missing_modality_table(records, paper_to_n),
            modality_degradation_chart(records, paper_to_n),
            ablation_table(records, paper_to_n),
            tradeoff_scatter(records, paper_to_n),
        )
        if b
    ]


def inject_quant_blocks(report: str, blocks: list[str]) -> str:
    """Chèn các khối trước mục 5.5 (hoặc trước mục 6, hoặc cuối bài) — không tạo mục mới."""
    if not blocks:
        return report
    marker = re.search(r"^###\s*5\.5\b", report, re.M) or re.search(r"^##\s*6\.", report, re.M)
    text = "\n\n".join(blocks) + "\n\n"
    return report[: marker.start()] + text + report[marker.start():] if marker else report.rstrip() + "\n\n" + text
