"""Phase 2 — Quantitative Evidence Ledger dựng bằng code từ `ResultRecord` (không để LLM tự ghi số).

Cột: Source [n] | Method | Dataset | Metric | Value | Notes. Trường paper không nêu → "NR" (Not Reported).
Metric Dice/HD95 theo vùng (WT/TC/ET): nếu paper có một vài vùng mà thiếu vùng khác, vùng thiếu được ghi NR thay vì bỏ trống.
"""

from __future__ import annotations

import re

from app.agent.evidence.quant_check import ResultRecord, validate_record

NR = "NR"
HEADER = "| Source [n] | Method | Dataset | Metric | Value | Notes |\n|---|---|---|---|---|---|"
_REGION_SET = ("WT", "TC", "ET")
_REGIONAL_METRICS = ("Dice", "HD95")
_LEDGER_RE = re.compile(r"\n*#{1,6}\s*Quantitative Evidence Ledger.*\Z", re.IGNORECASE | re.DOTALL)
EMPTY_LINE = "No quantitative results reported in the retrieved evidence"


def _fmt(value: float) -> str:
    return f"{value:g}"


def _dataset_label(rec: ResultRecord) -> str:
    return " ".join(x for x in (rec.dataset, rec.dataset_version) if x) or NR


def _metric_label(rec: ResultRecord) -> str:
    return " ".join(x for x in (rec.metric, rec.region) if x)


def _notes(rec: ResultRecord) -> str:
    notes = [f"unit={rec.unit}" if rec.unit else "unit NR"]
    if rec.spread is not None and rec.spread_type:
        notes.append(f"±{_fmt(rec.spread)} ({rec.spread_type})")
    if rec.split:
        notes.append(f"split {rec.split}")
    if rec.source_page is not None:
        notes.append(f"p.{rec.source_page}")
    if rec.source_table:
        notes.append(rec.source_table)
    notes += [p for p in validate_record(rec) if "nguồn" not in p and "đơn vị" not in p]
    return "; ".join(notes)


def render_ledger(records: list[ResultRecord], paper_to_n: dict[str, int]) -> str:
    """Bảng ledger Markdown. Bản ghi biến thể ablation không đưa vào (xem quant_analysis); paper không có [n] bị bỏ."""
    main = [r for r in records if not r.variant and r.paper_id in paper_to_n]
    if not main:
        return f"## Quantitative Evidence Ledger\n\n{EMPTY_LINE}.\n"
    rows: list[tuple[int, str, str, str, str, str]] = []
    present: dict[tuple[str, str, str, str], set[str]] = {}
    for rec in main:
        n = paper_to_n[rec.paper_id]
        rows.append((n, rec.model or NR, _dataset_label(rec), _metric_label(rec), _fmt(rec.value), _notes(rec)))
        if rec.metric in _REGIONAL_METRICS and rec.region in _REGION_SET:
            present.setdefault((rec.paper_id, rec.model, _dataset_label(rec), rec.metric), set()).add(rec.region or "")
    for (pid, model, ds, metric), regions in present.items():
        for region in _REGION_SET:
            if region not in regions:
                rows.append((paper_to_n[pid], model or NR, ds, f"{metric} {region}", NR, "Not Reported in the source"))
    rows.sort(key=lambda r: (r[0], r[2], r[3]))
    body = "\n".join(f"| [{n}] | {m} | {d} | {metric} | {v} | {notes} |" for n, m, d, metric, v, notes in rows)
    return f"## Quantitative Evidence Ledger\n\n{HEADER}\n{body}\n"


def replace_ledger(draft: str, ledger: str) -> str:
    """Thay mục ledger do LLM tự viết (nếu có) bằng bản dựng từ record; nếu chưa có thì nối vào cuối."""
    return _LEDGER_RE.sub("", draft).rstrip() + "\n\n" + ledger
