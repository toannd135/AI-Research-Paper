"""Gỡ ô số không truy vết được khỏi bảng của bản cuối (không để số không có nguồn lọt vào PDF).

Quality Gate chỉ báo `UNTRACED`; bước này sửa: ô số trong khối ```table mà giá trị không xuất hiện nguyên văn trong
chunk của paper được cite → thay bằng `NR` và bổ sung định nghĩa vào caption. Không tự thay bằng số khác, không đụng bảng
`derived` (số suy ra từ bản ghi đã kiểm chứng), năm, hay ô đã TRACED. Biểu đồ không bị sửa ở đây (đã có kiểm tra comparability).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agent.evidence.traceability import UNTRACED

logger = logging.getLogger(__name__)

REDACTED = "NR"
CAPTION_NOTE = (
    " NR = value withdrawn: it could not be found verbatim in the retrieved passages of the cited source "
    "(this does not mean the source omits it)."
)
_BLOCK_RE = re.compile(r"```(table|chart)\s*\n(.*?)```", re.DOTALL)
_LOCATION_RE = re.compile(r"^row (\d+), (.*)$")
_NUMBER_RE = re.compile(r"^\**\s*(\d+(?:\.\d+)?)\s*%?\s*\**$")


def _untraced_by_block(records: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    for r in records:
        m = re.fullmatch(r"table#(\d+)", str(r.get("block", "")))
        if r.get("status") == UNTRACED and m and _LOCATION_RE.match(str(r.get("location", ""))):
            out.setdefault(int(m.group(1)), []).append(r)
    return out


def redact_untraced_cells(text: str, records: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Trả về (văn bản đã gỡ, danh sách ô đã gỡ). `records` là kết quả `trace_claims` trên CHÍNH `text` này."""
    targets = _untraced_by_block(records)
    if not targets:
        return text, []
    removed: list[dict[str, Any]] = []
    counter = 0

    def _sub(m: re.Match) -> str:
        nonlocal counter
        counter += 1  # cùng cách đếm với extract_numeric_claims: mọi khối table/chart theo thứ tự
        if m.group(1) != "table" or counter not in targets:
            return m.group(0)
        try:
            spec = json.loads(m.group(2))
        except ValueError:
            return m.group(0)
        if not isinstance(spec, dict) or spec.get("derived") or not isinstance(spec.get("rows"), list):
            return m.group(0)
        columns = [str(c) for c in spec.get("columns") or []]
        changed = 0
        for rec in targets[counter]:
            row_no, col_name = _LOCATION_RE.match(rec["location"]).groups()
            row = spec["rows"][int(row_no) - 1] if 0 < int(row_no) <= len(spec["rows"]) else None
            if not isinstance(row, list):
                continue
            for idx, cell in enumerate(row):
                cell_match = _NUMBER_RE.match(str(cell).strip())
                name = columns[idx] if idx < len(columns) else f"col{idx + 1}"
                if cell_match and name == col_name and abs(float(cell_match.group(1)) - float(rec["value"])) < 1e-9:
                    row[idx] = REDACTED
                    removed.append({"block": rec["block"], "location": rec["location"], "value": rec["value"], "cites": rec.get("cites", [])})
                    changed += 1
                    break
        if not changed:
            return m.group(0)
        caption = str(spec.get("caption", ""))
        if CAPTION_NOTE.strip() not in caption:
            spec["caption"] = caption.rstrip() + CAPTION_NOTE
        return f"```table\n{json.dumps(spec, ensure_ascii=False)}\n```"

    out = _BLOCK_RE.sub(_sub, text)
    if removed:
        logger.warning("Gỡ %d ô số không truy vết được khỏi bảng (thay bằng %s)", len(removed), REDACTED)
    return out, removed
