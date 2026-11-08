"""Truy vết số liệu trong bảng/biểu đồ của bài về văn bản PDF nguồn (trang, hash PDF).

Chuỗi bằng chứng: số trong bảng → [n] của hàng/caption → paper → chunk chứa đúng con số đó (trang) → sha256 của PDF.
Chỉ so khớp con số NGUYÊN VĂN (không đổi % ↔ tỷ lệ); không khớp = UNTRACED, không bao giờ tự sửa số.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

TRACED = "TRACED"
UNTRACED = "UNTRACED"
NO_CITATION = "NO_CITATION"

_BLOCK_RE = re.compile(r"```(table|chart)\s*\n(.*?)```", re.DOTALL)
_CITE_RE = re.compile(r"\[(\d+)\]")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_NUMERIC_CELL_RE = re.compile(r"^\**\s*(\d+(?:\.\d+)?)\s*%?\s*\**$")
_CHUNK = 1024 * 1024


def _is_year(raw: str) -> bool:
    return "." not in raw and raw.isdigit() and 1900 <= int(raw) <= 2100


def extract_numeric_claims(text: str) -> list[dict[str, Any]]:
    """Mọi giá trị số trong khối ```table / ```chart, kèm [n] của hàng (bảng) hoặc caption (biểu đồ)."""
    claims: list[dict[str, Any]] = []
    for block_idx, match in enumerate(_BLOCK_RE.finditer(text), start=1):
        kind, raw = match.group(1), match.group(2)
        try:
            spec = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(spec, dict) or spec.get("derived"):
            continue  # bảng số suy ra (Δ) không phải số trích từ PDF
        caption_cites = [int(n) for n in _CITE_RE.findall(str(spec.get("caption", "")))]
        if kind == "table":
            columns = spec.get("columns") if isinstance(spec.get("columns"), list) else []
            for row_idx, row in enumerate(spec.get("rows") or [], start=1):
                if not isinstance(row, list):
                    continue
                cites = [int(n) for c in row for n in _CITE_RE.findall(str(c))] or caption_cites
                for col_idx, cell in enumerate(row):
                    m = _NUMERIC_CELL_RE.match(str(cell).strip())
                    if m and not _is_year(m.group(1)):
                        col = str(columns[col_idx]) if col_idx < len(columns) else f"col{col_idx + 1}"
                        claims.append({"block": f"table#{block_idx}", "location": f"row {row_idx}, {col}", "value": m.group(1), "cites": cites})
        else:
            for s_idx, series in enumerate(spec.get("series") or [], start=1):
                values = series.get("values") if isinstance(series, dict) else None
                for v_idx, value in enumerate(values or [], start=1):
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        claims.append({"block": f"chart#{block_idx}", "location": f"series {s_idx}, point {v_idx}", "value": repr(value), "cites": caption_cites})
    return claims


def pdf_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def trace_claims(claims: list[dict[str, Any]], sources: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """`sources[n]` = {"paper_id", "chunks": [{"page", "text"}], "pdf_sha256"}; trả về bản ghi bằng chứng cho từng giá trị."""
    records: list[dict[str, Any]] = []
    for claim in claims:
        value = float(claim["value"])
        record = {k: claim[k] for k in ("block", "location", "value", "cites")} | {"status": UNTRACED, "paper_id": None, "pages": [], "pdf_sha256": None}
        if not claim["cites"]:
            record["status"] = NO_CITATION
        for n in claim["cites"]:
            src = sources.get(n)
            if not src:
                continue
            pages = sorted({c.get("page") for c in src["chunks"] if any(abs(float(x) - value) < 1e-9 for x in _NUMBER_RE.findall(c.get("text", "")))} - {None})
            found = any(abs(float(x) - value) < 1e-9 for c in src["chunks"] for x in _NUMBER_RE.findall(c.get("text", "")))
            if found:
                record.update(status=TRACED, paper_id=src["paper_id"], pages=pages, pdf_sha256=src.get("pdf_sha256"))
                break
        records.append(record)
    return records
