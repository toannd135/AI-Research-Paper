"""Xuất Evidence Ledger ra CSV làm supplementary: mỗi dòng là một bản ghi số liệu kèm nguồn (paper, trang, bảng).

Dựng từ `state["results"]` (các ResultRecord đã kiểm chứng nguyên văn trong PDF); không ghi lại số nào ngoài bản ghi.
"""

from __future__ import annotations

import csv
from dataclasses import fields
from pathlib import Path
from typing import Any

from app.agent.evidence.quant_check import ResultRecord, validate_record

_FIELDS = [f.name for f in fields(ResultRecord)]
COLUMNS = ["paper_file", *_FIELDS, "variant_is_ablation", "issues"]


def export_ledger_csv(results: list[dict[str, Any]], path: Path, paper_files: dict[str, str] | None = None) -> int:
    """Ghi CSV UTF-8 (có BOM để Excel đọc đúng); trả về số dòng đã ghi. `paper_files`: paper_id -> tên tệp PDF."""
    from app.agent.evidence.extractor import records_from_dicts

    records = records_from_dicts(results)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for rec in records:
            row = [
                (", ".join(v) if isinstance(v, tuple) else ("" if v is None else v))
                for v in (getattr(rec, n) for n in _FIELDS)
            ]
            writer.writerow(
                [
                    (paper_files or {}).get(rec.paper_id, ""),
                    *row,
                    "yes" if rec.variant else "no",
                    "; ".join(validate_record(rec)),
                ]
            )
    return len(records)
