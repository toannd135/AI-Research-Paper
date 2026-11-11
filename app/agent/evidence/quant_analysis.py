"""Phase 4 — phân tích định lượng suy ra từ `ResultRecord` (không từ LLM): Δ so với tốt nhất, Δ ablation, đánh đổi Dice–Params.

Chỉ sinh khối khi đủ điều kiện (≥3 phương pháp CÙNG dataset/version/split/vùng/metric/đơn vị); số suy ra được gắn
`"derived": true` để traceability/scrub không coi là số trích từ PDF. Không bao giờ tạo số giả để lấp biểu đồ.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.evidence import study_profile as sp
from app.agent.evidence.quant_check import ResultRecord, group_comparable
from app.agent.evidence.stats import lower_is_better

MIN_METHODS = 3
MIN_SCATTER_POINTS = 4
MAX_PANELS = 4
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
                f"{r.model} [{paper_to_n[r.paper_id]}]", _setting(r), f"{sample.metric} {sample.region}", f"{r.value:g}", f"{r.value - best:+.2f}", _spread_cell(r),
            ])
    if not rows:
        return None
    caption = "Gap to the best reported value within each directly comparable setting (derived from the cited values; unit as in the sources)"
    columns = ["Method [Ref]", "Setting", "Metric", "Value", "Δ vs best", "Spread"]
    if all(row[-1] == "NR" for row in rows):  # không nguồn nào báo sai số: bỏ cột thay vì in toàn NR
        columns, rows = columns[:-1], [row[:-1] for row in rows]
    else:
        caption += "; spread = the ± value printed in the source with its stated type (SD, SE or 95% CI), NR = not reported"
    return _block("table", {"caption": caption, "columns": columns, "rows": rows, "derived": True})


def _spread_cell(rec: ResultRecord) -> str:
    return f"±{rec.spread:g} ({rec.spread_type})" if rec.spread is not None and rec.spread_type else "NR"


_EFFICIENCY_METRICS = (
    ("params", "Params"), ("parameters", "Params"), ("gflops", "GFLOPs"), ("flops", "GFLOPs"), ("inferencetime", "Inference time"),
    ("latency", "Inference time"), ("inferencelatency", "Inference time"), ("trainingtime", "Training time"),
    ("trainingtimeperepoch", "Training time"), ("gpumemory", "GPU memory"), ("memory", "GPU memory"), ("energy", "Energy"),
)
_BASE_COST_COLUMNS = ("Params", "GFLOPs", "Inference time")
_EXTRA_COST_COLUMNS = ("Training time", "GPU memory", "Energy")  # chỉ thêm cột khi có nguồn báo


def efficiency_table(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str | None:
    """Params / GFLOPs / thời gian suy luận theo phương pháp, đúng như nguồn báo; ô thiếu = NR, không ước lượng."""
    canon = dict(_EFFICIENCY_METRICS)
    per_model: dict[tuple[str, str], dict[str, str]] = {}
    for r in records:
        col = canon.get(re.sub(r"[\s_-]+", "", r.metric.lower()))
        if col is None or r.variant or r.paper_id not in paper_to_n:
            continue
        per_model.setdefault((r.paper_id, r.model), {}).setdefault(col, f"{r.value:g} {r.unit or ''}".strip())
    present = {c for cells in per_model.values() for c in cells}
    cols = [*_BASE_COST_COLUMNS, *(c for c in _EXTRA_COST_COLUMNS if c in present)]
    rows = [
        [f"{model} [{paper_to_n[pid]}]", *(cells.get(c, "NR") for c in cols)]
        for (pid, model), cells in sorted(per_model.items(), key=lambda kv: (paper_to_n[kv[0][0]], kv[0][1]))
        if model
    ]
    if len(rows) < 2:
        return None
    caption = (
        "Computational cost as reported by each source (NR = not reported); hardware, input size and units differ between sources, "
        "so values are not directly comparable across rows. The NR pattern itself shows which cost dimensions the literature reports"
    )
    return _block("table", {"caption": caption, "columns": ["Method [Ref]", *cols], "rows": rows[: MAX_ROWS * 3], "derived": True})


def ablation_table(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str | None:
    """Δ(biến thể − mô hình đầy đủ) khi cùng paper, model, dataset/version/split, vùng, metric, đơn vị."""
    full = {_key(r): r for r in records if not r.variant}
    rows: list[list[str]] = []
    for r in records:
        base = full.get(_key(r)) if r.variant else None
        if base is None or r.paper_id not in paper_to_n or _variant_modalities(r.variant) is not None:
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
    # < MIN_SCATTER_POINTS phương pháp: không thể hiện được quan hệ/đường biên đánh đổi → bảng chi phí (efficiency_table) đảm nhận
    if not best or len({x[0].model for x in best[1]}) < MIN_SCATTER_POINTS:
        return None
    (ds, ver, split, region, unit, p_unit), pairs = best
    seen: dict[str, tuple[ResultRecord, ResultRecord]] = {}
    for d, p in pairs:
        seen.setdefault(d.model, (d, p))
    series = [{"name": f"{m} [{paper_to_n[d.paper_id]}]", "x": [p.value], "y": [d.value]} for m, (d, p) in seen.items()]
    cites = ", ".join(sorted({f"[{paper_to_n[d.paper_id]}]" for d, _ in seen.values()}))
    caption = f"Dice ({region}) versus parameter count on {ds} {ver} ({split}) {cites}"
    return _block("chart", {"type": "scatter", "caption": caption, "x_label": f"Parameters ({p_unit})", "y_label": f"Dice {region} ({unit})", "series": series})


FULL_MODALITIES = frozenset({"T1", "T1c", "T2", "FLAIR"})
_MODALITY_ORDER = ("T1", "T1c", "T2", "FLAIR")
# Cách viết gặp trong paper -> tên chuẩn (khóa đã bỏ khoảng trắng, '-', '_', '.', '(', ')')
_MODALITY_ALIASES = {
    "T1": ("t1", "t1w", "t1weighted", "nativet1", "t1native", "t1pre", "t1precontrast", "precontrastt1"),
    "T1c": (
        "t1c", "t1ce", "t1gd", "t1+c", "t1wce", "t1cw", "cet1", "t1post", "t1postcontrast", "postcontrastt1", "t1contrast",
        "contrastenhancedt1", "t1contrastenhanced", "t1enhanced", "t1gadolinium", "gadoliniumt1", "t1weightedcontrastenhanced",
    ),
    "T2": ("t2", "t2w", "t2weighted"),
    "FLAIR": ("flair", "t2flair", "flairt2", "t2weightedflair"),
}
_MODALITY_CANON = {alias: canon for canon, aliases in _MODALITY_ALIASES.items() for alias in aliases}


def canon_modality(name: str) -> str | None:
    """Tên modality chuẩn (T1/T1c/T2/FLAIR) hoặc None nếu không nhận ra — không đoán."""
    key = re.sub(r"[\s_\-().]|modalit(?:y|ies)|sequences?|images?|mri", "", str(name).lower())
    return _MODALITY_CANON.get(key)


def _modality_set(rec: ResultRecord) -> frozenset[str]:
    """Tập modality chuẩn hóa của bản ghi; rỗng nếu không có hoặc có tên không nhận ra (không đoán)."""
    mods = {canon_modality(m) for m in rec.modality}
    return frozenset(mods) if mods and None not in mods else frozenset()


_MISSING_VARIANT_RE = re.compile(
    r"^\s*(?:missing|without|w/o|no|drop(?:ped|ping)?|absent|remov(?:e|ed|ing)|exclud(?:e|ed|ing)|minus)\b[:\s]*(?P<names>.+?)\s*$", re.IGNORECASE
)
_AVAILABLE_VARIANT_RE = re.compile(
    r"^\s*(?:(?:with|using)\s+only|only|available|observed|inputs?|using)\b[:\s]*(?P<names>.+?)\s*$"
    r"|^\s*(?P<names2>.+?)[\s-]+only\s*$",
    re.IGNORECASE,
)
_FULL_VARIANT_RE = re.compile(r"^\s*(?:full|all|complete)(?:\s+(?:modalities|modality|inputs?|sequences))?\s*$", re.IGNORECASE)
_MODALITY_SPLIT_RE = re.compile(r"\s*(?:,|;|&|/|\+|\band\b|\bor\b)\s*", re.IGNORECASE)


def _parse_modalities(text: str) -> frozenset[str] | None:
    """'T1, T2 and FLAIR' / 'T1ce+FLAIR' -> tập chuẩn; None nếu có tên không nhận ra."""
    text = re.sub(r"t1\s*\+\s*c\b", "T1c", text, flags=re.IGNORECASE)  # 'T1+C' là một modality, không phải phép cộng
    names = [n for n in _MODALITY_SPLIT_RE.split(text) if n.strip()]
    mods = {canon_modality(n) for n in names}
    return frozenset(mods) if mods and None not in mods else None


def _variant_modalities(variant: str | None) -> frozenset[str] | None:
    """Tập modality CÒN LẠI mà biến thể mô tả; None nếu biến thể không nói về modality hoặc có tên lạ (không đoán).

    Nhận cả cách viết theo modality bị bỏ ('Missing T1c', 'w/o T1 and T2', 'missing T1, T2, FLAIR') lẫn theo modality còn
    lại ('FLAIR only', 'only T1ce+FLAIR', 'available: T1, T2'). Extractor hay ghi các thí nghiệm này vào `variant`.
    """
    v = variant or ""
    if _FULL_VARIANT_RE.match(v):
        return FULL_MODALITIES
    m = _MISSING_VARIANT_RE.match(v)
    if m:
        dropped = _parse_modalities(m.group("names"))
        rest = FULL_MODALITIES - dropped if dropped else frozenset()
        return frozenset(rest) if rest and rest != FULL_MODALITIES else None
    m = _AVAILABLE_VARIANT_RE.match(v)
    if m:
        kept = _parse_modalities(m.group("names") or m.group("names2") or "")
        return kept or None
    return None


def _subset_label(mods: frozenset[str]) -> str:
    if mods == FULL_MODALITIES:
        return "Full (T1, T1c, T2, FLAIR)"
    return "+".join(m for m in _MODALITY_ORDER if m in mods)


def _modality_groups(records: list[ResultRecord], paper_to_n: dict[str, int]) -> dict[tuple, dict[frozenset[str], ResultRecord]]:
    """Nhóm theo (paper, model, dataset, version, split, vùng, metric, đơn vị) -> {tập modality: bản ghi}; chỉ giữ nhóm có ≥2 tập."""
    groups: dict[tuple, dict[frozenset[str], ResultRecord]] = {}
    # khóa có thí nghiệm "Missing X": bản ghi không variant cùng khóa chính là kết quả đủ 4 modality của chính nguồn đó
    ablated = {_key(r) for r in records if _variant_modalities(r.variant) is not None}
    for r in records:
        if r.paper_id not in paper_to_n:
            continue
        if r.variant:
            mods = _variant_modalities(r.variant) or frozenset()
        else:
            mods = _modality_set(r) or (FULL_MODALITIES if _key(r) in ablated and not r.modality else frozenset())
        if not mods:
            continue
        groups.setdefault(_key(r), {}).setdefault(mods, r)
    return {k: v for k, v in groups.items() if len(v) >= 2}


def missing_modality_record_count(records: list[ResultRecord], paper_to_n: dict[str, int]) -> int:
    """Số bản ghi có tập modality KHÔNG đủ 4 (biến thể 'Missing X' hoặc cột modality thiếu), kể cả khi chưa đủ 2 tập để thành nhóm ma trận."""
    count = 0
    for r in records:
        if r.paper_id not in paper_to_n:
            continue
        mods = _variant_modalities(r.variant) if r.variant else None
        mods = mods if mods is not None else _modality_set(r)
        if mods and mods != FULL_MODALITIES:
            count += 1
    return count


def modality_matrix_stats(records: list[ResultRecord], paper_to_n: dict[str, int]) -> dict[str, int]:
    """Số liệu thật về độ phủ missing-modality, dùng cho EVIDENCE LIMITS và kiểm tra."""
    groups = _modality_groups(records, paper_to_n)
    with_full = sum(1 for g in groups.values() if FULL_MODALITIES in g)
    subsets = {s for g in groups.values() for s in g}
    singles = {next(iter(s)) for s in subsets if len(s) == 1}
    settings: dict[tuple, set[str]] = {}
    for key in groups:
        settings.setdefault(key[2:], set()).add(key[0])  # (dataset, version, split, vùng, metric, đơn vị) -> các paper
    return {
        "groups": len(groups),
        "groups_with_full": with_full,
        "distinct_subsets": len(subsets),
        "single_modalities": len(singles),
        "sources": len({k[0] for k in groups}),
        "possible_subsets": 2 ** len(FULL_MODALITIES) - 1,
        "groups_all_subsets": sum(1 for g in groups.values() if len(g) >= 2 ** len(FULL_MODALITIES) - 1),
        "shared_settings": sum(1 for papers in settings.values() if len(papers) >= 2),
        "subset_labels": sorted(_subset_label(x) for x in subsets),
    }


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


MAX_MATRIX_COLUMNS = 6


def _all_subsets() -> list[frozenset[str]]:
    from itertools import combinations

    subs = [frozenset(c) for k in range(len(_MODALITY_ORDER), 0, -1) for c in combinations(_MODALITY_ORDER, k)]
    return sorted(subs, key=lambda x: (-len(x), [_MODALITY_ORDER.index(m) for m in sorted(x, key=_MODALITY_ORDER.index)]))


def modality_coverage_matrix(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str | None:
    """Ma trận đủ 2^4−1 = 15 tập modality × (phương pháp, vùng, metric): giá trị đã báo hoặc NR; không nội suy ô nào.

    Mỗi cột gắn nhãn bối cảnh (A, B…) = dataset/version/split/vùng/metric/đơn vị; khác nhãn = không so sánh được.
    Δ chỉ tính so với kết quả full-modality của CHÍNH nguồn đó.
    """
    groups = _modality_groups(records, paper_to_n)
    if not groups:
        return None
    chosen = sorted(groups.items(), key=lambda kv: (-len(kv[1]), paper_to_n[kv[0][0]], str(kv[0][1]), str(kv[0][5])))[:MAX_MATRIX_COLUMNS]
    letters: dict[tuple, str] = {}
    for key, _ in chosen:
        letters.setdefault(key[2:], chr(ord("A") + len(letters)))
    columns = ["Available modalities"]
    for key, by_mods in chosen:
        r = next(iter(by_mods.values()))
        columns.append(f"{r.model} [{paper_to_n[r.paper_id]}] · {r.metric} {r.region or ''} · {letters[key[2:]]}".replace("  ", " "))
    rows: list[list[str]] = []
    for subset in _all_subsets():
        row = [_subset_label(subset)]
        for _, by_mods in chosen:
            rec, full = by_mods.get(subset), by_mods.get(FULL_MODALITIES)
            if rec is None:
                row.append("NR")
            elif full is None or subset == FULL_MODALITIES:
                row.append(f"{rec.value:g}")
            else:
                row.append(f"{rec.value:g} ({rec.value - full.value:+.3g})")
        rows.append(row)
    rows.append(["Subsets reported", *(f"{len(by_mods)}/{len(rows)}" for _, by_mods in chosen)])
    legend = "; ".join(
        f"{letter} = " + " ".join(x for x in (ds, ver, split and f"({split})", region, metric, unit and f"[{unit}]") if x)
        for (ds, ver, split, region, metric, unit), letter in letters.items()
    )
    caption = (
        f"Reported results for all {len(rows) - 1} non-empty subsets of the four MRI sequences: value (Δ vs. the same source's full-modality result). "
        "NR = not reported in the results extracted from that source (it does not mean the subset was not evaluated); no cell is imputed. "
        f"Settings: {legend}. Columns with different setting letters are not comparable."
    )
    return _block("table", {"caption": caption, "columns": columns, "rows": rows, "derived": True})


MAX_HEATMAP_MODELS = 5  # số cột tối đa của heatmap (một cột trang vẫn đọc được)


def modality_degradation_chart(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str | None:
    """Heatmap độ bền khi thiếu modality: hàng = 14 tập modality thiếu, cột = phương pháp, ô = Δ so với kết quả full-modality
    của CHÍNH nguồn đó; ô không báo cáo = null (NR, không nội suy). Chỉ một setting (cùng dataset/version/split/vùng/metric/đơn vị)
    để không đặt các protocol khác nhau cạnh nhau như thể so sánh được."""
    by_setting: dict[tuple, list[dict[frozenset[str], ResultRecord]]] = {}
    for key, by_mods in _modality_groups(records, paper_to_n).items():
        if FULL_MODALITIES in by_mods and len(by_mods) >= 3:  # cần mốc full + ≥2 tập thiếu
            by_setting.setdefault(key[2:], []).append(by_mods)
    if not by_setting:
        return None
    setting, models = max(by_setting.items(), key=lambda kv: (sum(len(m) for m in kv[1]), len(kv[1])))
    models = sorted(models, key=lambda m: (-len(m), paper_to_n[next(iter(m.values())).paper_id]))[:MAX_HEATMAP_MODELS]
    subsets = [x for x in _all_subsets() if x != FULL_MODALITIES]
    matrix = [
        [round(m[x].value - m[FULL_MODALITIES].value, 4) if x in m else None for m in models]
        for x in subsets
    ]
    labels = []
    for m in models:
        full = m[FULL_MODALITIES]
        labels.append(f"{full.model} [{paper_to_n[full.paper_id]}] (full {full.value:g})")
    ds, ver, split, region, metric, unit = setting
    setting_txt = " ".join(x for x in (ds, ver, split and f"({split})") if x)
    cites = ", ".join(f"[{n}]" for n in sorted({paper_to_n[next(iter(m.values())).paper_id] for m in models}))
    reported = sum(v is not None for r in matrix for v in r)
    caption = (
        f"Missing-modality robustness: change in {metric} {region or ''} ({unit or 'as reported'}) relative to each source's own "
        f"full-modality result, for every subset of the four MRI sequences, on {setting_txt} {cites}. "
        f"NR = not reported in the extracted results ({reported}/{len(matrix) * len(models)} cells reported); no cell is imputed. "
        "Only methods evaluated under this single setting are shown; results under other protocols are not comparable."
    ).replace("  ", " ")
    return _block("chart", {
        "type": "heatmap", "caption": caption, "x_labels": labels, "y_labels": [_subset_label(x) for x in subsets],
        "matrix": matrix, "c_label": f"Δ {metric}", "derived": True,
    })


def evidence_limits(
    records: list[ResultRecord], paper_to_n: dict[str, int], n_papers: int, attrs_by_paper: dict[str, dict[str, dict[str, Any]]] | None = None
) -> str:
    """Các giới hạn THẬT của số liệu đã trích, để chương Limitations nêu đúng thay vì bịa hoặc bỏ qua."""
    stats = modality_matrix_stats(records, paper_to_n)
    lines = ["EVIDENCE LIMITS (computed from the extracted records; state these plainly in the Limitations and wherever a claim depends on them):"]
    with_spread = sum(1 for r in records if r.spread is not None)
    spread_txt = (
        "every value is a single reported point estimate (no standard deviation, confidence interval or significance test was extracted)"
        if with_spread == 0
        else f"only {with_spread} of them report a spread (SD/SE/95% CI) and none a significance test, so most comparisons rest on point estimates"
    )
    with_records = len({r.paper_id for r in records if r.paper_id in paper_to_n})
    lines.append(
        f"- {len(records)} verified numeric records were extracted from {with_records} of the {n_papers} cited papers; the other "
        f"{max(n_papers - with_records, 0)} contributed no record (no retrieved passage printed a metric value the extractor could verify), "
        "so the ledger is NOT an exhaustive record of every number in the corpus — never call it exhaustive or complete, and never say "
        f"'from {n_papers} papers' for it; {spread_txt}."
    )
    n_sub = stats["possible_subsets"]
    if stats["groups"] == 0:
        lines.append(
            "- No missing-modality result (a model evaluated with one or more MRI sequences absent) was extracted into the structured records. "
            "Do NOT write that no source reports such results: sources may still discuss modality importance in prose (cite those passages). "
            f"Say only that no quantitative degradation matrix (per-modality, all {n_sub} subsets, or cross-study) could be built from the extracted records."
        )
    else:
        cross = (
            f"a cross-study degradation matrix is possible only for the {stats['shared_settings']} setting(s) shared by ≥2 sources"
            if stats["shared_settings"]
            else "no two sources share the same dataset version/split/region/metric, so no cross-study degradation matrix can be built"
        )
        lines.append(
            "- Distinguish THREE levels of missing-modality evidence and never contradict the tables: "
            f"(a) per-modality ablation results WERE extracted from {stats['sources']} source(s) ({stats['groups']} method/setting groups, "
            f"{stats['groups_with_full']} with the same source's full-modality result; subsets observed: {', '.join(stats['subset_labels'])}); "
            f"(b) they cover {stats['distinct_subsets']} of the {n_sub} non-empty modality subsets, so a complete combinatorial matrix cannot be built; "
            f"(c) {cross}. Δ is given only where the same source reports both conditions."
        )
    if attrs_by_paper is not None:
        a = {pid: v for pid, v in attrs_by_paper.items() if pid in paper_to_n}
        lines.append(
            "- Reliability evidence found as explicit sentences in the retrieved passages (other sources: not found, which is NOT the same as not done): "
            f"external/multi-centre validation {sp.count(a, 'external_validation')}, cross-validation {sp.count(a, 'cross_validation')}, "
            f"patient-wise split {sp.count(a, 'patient_wise_split')}, uncertainty/calibration/OOD {sp.count(a, 'uncertainty')}, "
            f"random modality dropout {sp.count(a, 'missing_random')}, all modality subsets {sp.count(a, 'missing_all_subsets')}, "
            f"code availability {sp.count(a, 'code_available')} of {n_papers} sources. These are counts of sentences FOUND in the retrieved passages, "
            "so a count of 0 means 'not observed in the retrieved passages', never 'no study does this': phrase it that way and do not write "
            "'no method/study …' from a count alone. "
            + (
                f"The structured ledger itself holds {stats['groups_all_subsets']} method/setting group(s) with all {n_sub} subsets."
                if stats["groups_all_subsets"]
                else f"The structured ledger holds no method/setting group with all {n_sub} subsets, but a source may still evaluate them in text that was not extracted — "
                "if you state that a named method was evaluated on all subsets, that claim must come from its own cited passage, and you must not "
                "also state elsewhere that no method was."
            )
            + " Use these counts in the clinical-reliability and limitations discussion; never generalise beyond them."
        )
    lines.append(
        "- Statements about this review's own corpus or evidence base (counts of records, papers, what was or was not extracted) carry NO citation [n]; "
        "never cite a range such as [1]–[14] to support them."
    )
    return "\n".join(lines)


def _has(records: list[ResultRecord], pred) -> bool:
    return any(pred(r) for r in records)


def _missing_protocol(pid: str, groups: dict, attrs: dict[str, dict[str, Any]]) -> str:
    """Giao thức thiếu modality: từ số tập đã báo (record) và câu nguyên văn (random dropout / mọi tổ hợp)."""
    subsets = {m for k, g in groups.items() if k[0] == pid for m in g}
    total = 2 ** len(FULL_MODALITIES) - 1
    parts = []
    for name, label in (("missing_all_subsets", "All subsets"), ("missing_random", "Random dropout")):
        hit = attrs.get(name) or {}
        if hit.get("value") == sp.YES:
            parts.append(f"{label} (p. {hit['page']})" if hit.get("page") is not None else label)
    if subsets:
        parts.append(f"{len(subsets)}/{total} subsets reported")
    return "; ".join(parts) or sp.NR


def study_profile_table(
    records: list[ResultRecord],
    paper_to_n: dict[str, int],
    attrs_by_paper: dict[str, dict[str, dict[str, Any]]] | None = None,
    tiers: dict[str, str] | None = None,
) -> str | None:
    """Hồ sơ bằng chứng từng nguồn: dataset/version, thẩm định ngoài, CV, chia theo bệnh nhân, giao thức thiếu modality, sai số,
    uncertainty, code. Ô = 'Yes/No (p. X)' từ câu nguyên văn hoặc record; NR = không tìm thấy trong đoạn/kết quả đã trích.
    `tiers` (evidence_tiers.classify_evidence) → đánh dấu nguồn chỉ có số liệu trên dataset khác dataset đích."""
    tiers = tiers or {}
    attrs_by_paper = attrs_by_paper or {}
    by_paper: dict[str, list[ResultRecord]] = {pid: [] for pid in attrs_by_paper if pid in paper_to_n}
    for r in records:
        if r.paper_id in paper_to_n:
            by_paper.setdefault(r.paper_id, []).append(r)
    if len(by_paper) < 3:
        return None
    groups = _modality_groups(records, paper_to_n)
    rows: list[list[str]] = []
    for pid, recs in sorted(by_paper.items(), key=lambda kv: paper_to_n[kv[0]]):
        attrs = attrs_by_paper.get(pid, {})
        datasets = sorted({" ".join(x for x in (r.dataset, r.dataset_version) if x) for r in recs} - {""})
        cv = sp.cell(attrs, "cross_validation")
        if cv == sp.NR and _has(recs, lambda r: bool(r.split and re.search(r"fold|cross", r.split, re.I))):
            cv = "Yes (reported split)"
        variance = "Yes (± in results)" if _has(recs, lambda r: r.spread is not None) else sp.NR
        rows.append([
            f"[{paper_to_n[pid]}]",
            ("; ".join(datasets[:3]) or sp.NR) + (" (other dataset)" if tiers.get(pid) == "other_dataset" else ""),
            sp.cell(attrs, "external_validation"),
            cv,
            sp.cell(attrs, "patient_wise_split"),
            _missing_protocol(pid, groups, attrs),
            variance,
            sp.cell(attrs, "uncertainty"),
            sp.cell(attrs, "code_available"),
        ])
    caption = (
        "Evidence profile of each source. Yes/No (p. X) = stated in a sentence of that source on page X; "
        "NR = not found in the passages or results extracted from that source (it does not mean the study did not do it). "
        "Independent reproduction by third parties is not assessed because it cannot be determined from the source itself. "
        "This is descriptive support for quality appraisal, not a risk-of-bias score"
        + ("; '(other dataset)' = the source reports no result on the target benchmark (indirect evidence)" if "other_dataset" in tiers.values() else "")
    )
    columns = ["Ref", "Dataset (version)", "External validation", "Cross-validation", "Patient-wise split",
               "Missing-modality protocol", "Variance reported", "Uncertainty / calibration", "Code available"]
    if len(rows) > MAX_PROFILE_TABLE_ROWS:
        return _evidence_map(rows, columns)
    return _block("table", {"caption": caption, "columns": columns, "rows": rows, "derived": True})


MAX_PROFILE_TABLE_ROWS = 12  # nhiều nguồn hơn: bảng dài cả trang → thay bằng evidence map gọn


def _evidence_flag(cell: str) -> str:
    """'Yes (p. 4)' / 'Random dropout (p. 6)' / '3/15 subsets reported' → Yes; 'No (p. 2)' → No; còn lại NR."""
    if cell.startswith("No"):
        return sp.NO
    return sp.NR if cell == sp.NR else sp.YES


def _evidence_map(rows: list[list[str]], columns: list[str]) -> str:
    """Evidence map: tiêu chí × nguồn tái lập/độ tin cậy (Yes/No/NR từ câu nguyên văn), bỏ cột dataset (văn bản tự do)."""
    criteria = columns[2:]
    caption = (
        f"Evidence map of {len(rows)} sources: which reliability and reproducibility criteria each source reports. "
        "Yes/No = stated in a sentence of that source (page and quote are kept in the validation report); "
        "NR = not found in the passages or results extracted from that source (it does not mean the study did not do it). "
        "Descriptive support for quality appraisal, not a risk-of-bias score"
    )
    # tiêu chí theo hàng, nguồn theo cột: nhiều nguồn vẫn gọn trong một dải ngang thay vì một cột cao cả trang
    return _block("chart", {
        "type": "evidence_map", "caption": caption, "x_labels": [r[0] for r in rows], "y_labels": criteria,
        "matrix": [[_evidence_flag(r[2 + k]) for r in rows] for k in range(len(criteria))], "derived": True,
    })


def _is_cost_metric(metric: str) -> bool:
    return re.sub(r"[\s_-]+", "", metric.lower()) in dict(_EFFICIENCY_METRICS)


def protocol_panels(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str | None:
    """So sánh kết quả đầy đủ đầu vào theo TỪNG protocol: mỗi ô = một dataset/version/split/metric/đơn vị (≥3 phương pháp).

    Thay cho biểu đồ đặt nhiều protocol trên cùng một trục. Chỉ sinh khi có ≥2 setting đủ điều kiện (một setting thì bảng Δ đã
    đủ); series = vùng/metric con nên cùng màu ở mọi ô. Giá trị lấy nguyên từ record đã kiểm chứng, ô thiếu = null (NR).
    """
    by_setting: dict[tuple, dict[str, dict[str, float]]] = {}
    for r in records:
        if r.variant or r.paper_id not in paper_to_n or not (r.dataset and r.split and r.unit and r.model) or _is_cost_metric(r.metric):
            continue
        mods = _modality_set(r)
        if mods and mods != FULL_MODALITIES:
            continue
        key = (r.dataset, r.dataset_version, r.split, r.metric, r.unit)
        label = f"{r.model} [{paper_to_n[r.paper_id]}]"
        by_setting.setdefault(key, {}).setdefault(label, {}).setdefault(r.region or r.metric, r.value)
    eligible = sorted(((k, v) for k, v in by_setting.items() if len(v) >= MIN_METHODS), key=lambda kv: (-len(kv[1]), str(kv[0])))
    if len(eligible) < 2:
        return None
    panels = []
    cites: set[str] = set()
    for (ds, ver, split, metric, unit), models in eligible[:MAX_PANELS]:
        regions = list(dict.fromkeys(reg for vals in models.values() for reg in vals))
        low = lower_is_better(metric)
        first = regions[0]
        labels = sorted(models, key=lambda m: (models[m].get(first) is None, (models[m].get(first) or 0) * (1 if low else -1)))[:MAX_ROWS]
        cites.update(re.findall(r"\[\d+\]", " ".join(labels)))
        title = " ".join(x for x in (ds, ver, f"({split})") if x) + f" · {metric} [{unit}]"
        panels.append({
            "type": "dot", "title": title, "labels": labels, "x_label": f"{metric} ({unit})",
            "series": [{"name": reg, "values": [models[m].get(reg) for m in labels]} for reg in regions],
        })
    caption = (
        "Reported full-input results stratified by evaluation protocol: each panel is one dataset/version/split/metric/unit setting "
        f"({', '.join(sorted(cites, key=lambda c: int(c[1:-1])))}). Values are compared only within a panel; panels differ in "
        "protocol and are not comparable. Missing values are not imputed"
    )
    return _block("chart", {"type": "panels", "ncols": 2, "panels": panels, "caption": caption, "derived": True})


def build_quant_blocks(
    records: list[ResultRecord],
    paper_to_n: dict[str, int],
    attrs_by_paper: dict[str, dict[str, dict[str, Any]]] | None = None,
    tiers: dict[str, str] | None = None,
) -> list[str]:
    return [
        b
        for b in (
            delta_table(records, paper_to_n),
            protocol_panels(records, paper_to_n),
            modality_coverage_matrix(records, paper_to_n),
            modality_degradation_chart(records, paper_to_n),
            ablation_table(records, paper_to_n),
            tradeoff_scatter(records, paper_to_n),
            efficiency_table(records, paper_to_n),
            study_profile_table(records, paper_to_n, attrs_by_paper, tiers),
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
