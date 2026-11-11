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
            labels = spec.get("labels") if isinstance(spec.get("labels"), list) else spec.get("x_labels")
            labels = labels if isinstance(labels, list) else []
            for s_idx, series in enumerate(spec.get("series") or [], start=1):
                values = series.get("values") if isinstance(series, dict) else None
                name_cites = [int(n) for n in _CITE_RE.findall(str(series.get("name", "")))] if isinstance(series, dict) else []
                for v_idx, value in enumerate(values or [], start=1):
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        # Nguồn của một điểm = [n] ở nhãn của điểm đó, rồi tới tên series, cuối cùng mới tới caption:
                        # caption gộp nhiều [n] không được che một điểm gán nhầm nguồn.
                        label = str(labels[v_idx - 1]) if v_idx <= len(labels) else ""
                        cites = [int(n) for n in _CITE_RE.findall(label)] or name_cites or caption_cites
                        claims.append({"block": f"chart#{block_idx}", "location": f"series {s_idx}, point {v_idx}", "value": repr(value), "cites": cites})
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


def _same_value(a: float, b: float) -> bool:
    return abs(a - b) < 1e-9


def _misattribution(claim: dict[str, Any], cited_paper_ids: dict[int, str], owners: dict[str, set[float]]) -> list[str]:
    """Paper thật sự sở hữu giá trị của `claim` khi nó bị cite nhầm; rỗng = không có căn cứ kết luận cite nhầm.

    Cite nhầm khi: giá trị khớp record của paper khác, mọi paper được cite ĐÃ có record trong sổ cái nhưng không record nào khớp.
    Paper được cite chưa có record (extractor chưa trích) thì bỏ qua — không đủ căn cứ để chặn.
    """
    if not claim["cites"]:
        return []
    value = float(claim["value"])
    cited = {cited_paper_ids[n] for n in claim["cites"] if n in cited_paper_ids}
    if not cited or not all(pid in owners for pid in cited):
        return []
    if any(_same_value(value, v) for pid in cited for v in owners[pid]):
        return []
    return sorted(pid for pid, vals in owners.items() if any(_same_value(value, v) for v in vals))


def _owners(records: list[Any]) -> dict[str, set[float]]:
    owners: dict[str, set[float]] = {}
    for rec in records:
        owners.setdefault(rec.paper_id, set()).add(float(rec.value))
    return owners


def mark_misattributed(trace_records: list[dict[str, Any]], cited_paper_ids: dict[int, str], records: list[Any]) -> list[dict[str, Any]]:
    """Bản ghi TRACED nhưng sổ cái cho thấy giá trị thuộc paper khác → UNTRACED (kèm `misattributed_to`) để bước gỡ ô/điểm xử lý."""
    owners = _owners(records)
    for rec in trace_records:
        true_owners = _misattribution(rec, cited_paper_ids, owners) if rec["status"] == TRACED else []
        if true_owners:
            rec.update(status=UNTRACED, paper_id=None, pages=[], pdf_sha256=None, misattributed_to=true_owners)
    return trace_records


def check_record_attribution(claims: list[dict[str, Any]], cited_paper_ids: dict[int, str], records: list[Any]) -> list[str]:
    """Mô tả từng giá trị trong bảng/biểu đồ bị cite nhầm paper (đối chiếu sổ cái record)."""
    owners = _owners(records)
    problems: list[str] = []
    for claim in claims:
        true_owners = _misattribution(claim, cited_paper_ids, owners)
        if true_owners:
            problems.append(
                f"{claim['block']} {claim['location']}: giá trị {claim['value']} gắn {', '.join(f'[{n}]' for n in claim['cites'])} "
                f"nhưng sổ cái ghi giá trị này thuộc {', '.join(true_owners)}"
            )
    return problems
