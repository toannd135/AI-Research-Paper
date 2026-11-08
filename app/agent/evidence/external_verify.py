"""Xác minh độc lập References qua Crossref (tùy chọn, tắt mặc định). Chỉ VERIFIED khi khớp CẢ DOI lẫn tiêu đề.

`fetch` được tiêm vào (test không dùng mạng): fetch(doi) -> dict Crossref `message` hoặc None nếu không tìm thấy/lỗi mạng.
Lỗi mạng KHÔNG hạ trạng thái (giữ nguyên, ghi issue); tiêu đề lệch → CONFLICT.
"""

from __future__ import annotations

import difflib
import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from app.agent.evidence.reference_check import CATALOG_MATCHED, CONFLICT, VERIFIED, _norm_title

logger = logging.getLogger(__name__)
TITLE_SIMILARITY = 0.9


def crossref_fetch(doi: str, timeout: float = 8.0) -> dict[str, Any] | None:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.load(resp).get("message")
    except (OSError, ValueError):
        logger.warning("Crossref không trả kết quả cho DOI %s", doi)
        return None


def external_verify(
    refs: dict[str, Any], catalog: dict[str, dict[str, Any]], fetch: Callable[[str], dict[str, Any] | None] = crossref_fetch
) -> dict[str, Any]:
    """Nâng CATALOG_MATCHED → VERIFIED (khớp) hoặc → CONFLICT (DOI có thật nhưng tiêu đề khác); cập nhật `counts`."""
    for res in refs["references"]:
        meta = catalog.get(res["paper_id"]) or {}
        doi = str(meta.get("doi", "")).strip()
        if res["status"] != CATALOG_MATCHED or not doi:
            continue
        msg = fetch(doi)
        if not msg:
            res["issues"].append("không xác minh được qua Crossref (lỗi mạng hoặc DOI không có)")
            continue
        titles = msg.get("title") or []
        remote = _norm_title(str(titles[0])) if titles else ""
        ratio = difflib.SequenceMatcher(None, _norm_title(str(meta.get("title", ""))), remote).ratio() if remote else 0.0
        if ratio >= TITLE_SIMILARITY:
            res["status"] = VERIFIED
        else:
            res["status"] = CONFLICT
            res["issues"].append(f"DOI tồn tại nhưng tiêu đề Crossref khác catalog (độ giống {ratio:.2f})")
    refs["counts"] = {}
    for res in refs["references"]:
        refs["counts"][res["status"]] = refs["counts"].get(res["status"], 0) + 1
    return refs
