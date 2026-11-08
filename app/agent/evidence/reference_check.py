"""Xác minh tài liệu tham khảo ở mức metadata (lớp A), chỉ dựa trên catalog nội bộ — không gọi mạng.

Trạng thái: CATALOG_MATCHED (đủ metadata trong catalog nội bộ) | PARTIALLY_VERIFIED | UNVERIFIED | CONFLICT | INVALID;
VERIFIED chỉ do `external_verify` cấp khi Crossref khớp cả DOI lẫn tiêu đề. Không bao giờ nâng trạng thái chỉ vì tiêu đề "có vẻ hợp lý".
"""

from __future__ import annotations

import re
from typing import Any

VERIFIED = "VERIFIED"  # chỉ do external_verify cấp
CATALOG_MATCHED = "CATALOG_MATCHED"
PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
UNVERIFIED = "UNVERIFIED"
CONFLICT = "CONFLICT"
INVALID = "INVALID"

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _norm_title(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", title.lower()).split())


PREPRINT = "preprint"
PUBLISHED = "published"
UNKNOWN_PUBLICATION = "unknown"
_PREPRINT_RE = re.compile(r"arxiv|preprint|biorxiv|medrxiv|ssrn|researchsquare", re.IGNORECASE)


def classify_publication(meta: dict[str, Any] | None) -> str:
    """preprint | published | unknown, chỉ từ venue/URL/DOI trong catalog (không đoán). Có venue không phải kho preprint -> published."""
    if not meta:
        return UNKNOWN_PUBLICATION
    venue = str(meta.get("venue", "")).strip()
    url = str(meta.get("url", "")).strip()
    doi = str(meta.get("doi", "")).strip()
    if venue and not _PREPRINT_RE.search(venue):
        return PUBLISHED
    if _PREPRINT_RE.search(venue) or _PREPRINT_RE.search(url):
        return PREPRINT
    return PUBLISHED if doi and not doi.lower().startswith("10.48550/arxiv") else UNKNOWN_PUBLICATION


def verify_reference(paper_id: str, meta: dict[str, Any] | None) -> dict[str, Any]:
    """Trạng thái của MỘT paper; `meta` là mục của catalog (None nếu không có)."""
    if not meta:
        return {"paper_id": paper_id, "status": UNVERIFIED, "missing": ["catalog"], "issues": ["không có metadata trong catalog"], "publication": UNKNOWN_PUBLICATION}
    missing = [f for f in ("title", "authors", "year") if not str(meta.get(f, "")).strip()]
    if not any(str(meta.get(f, "")).strip() for f in ("doi", "url", "venue")):
        missing.append("doi/url/venue")
    issues: list[str] = []
    doi = str(meta.get("doi", "")).strip()
    if doi and not _DOI_RE.match(doi):
        return {"paper_id": paper_id, "status": INVALID, "missing": missing, "issues": [f"DOI sai định dạng: {doi}"], "publication": classify_publication(meta)}
    year = str(meta.get("year", "")).strip()
    if year and not _YEAR_RE.match(year):
        return {"paper_id": paper_id, "status": INVALID, "missing": missing, "issues": [f"năm không hợp lệ: {year}"], "publication": classify_publication(meta)}
    status = CATALOG_MATCHED if not missing else PARTIALLY_VERIFIED
    return {"paper_id": paper_id, "status": status, "missing": missing, "issues": issues, "publication": classify_publication(meta)}


def verify_references(paper_ids: list[str], catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Xác minh các paper được trích dẫn; phát hiện trùng (cùng tiêu đề chuẩn hóa) → CONFLICT."""
    results = [verify_reference(pid, catalog.get(pid)) for pid in dict.fromkeys(paper_ids)]
    by_title: dict[str, list[dict[str, Any]]] = {}
    for res in results:
        title = str((catalog.get(res["paper_id"]) or {}).get("title", "")).strip()
        if title:
            by_title.setdefault(_norm_title(title), []).append(res)
    duplicates = [group for group in by_title.values() if len(group) > 1]
    for group in duplicates:
        for res in group:
            res["status"] = CONFLICT
            res["issues"].append("trùng tiêu đề với paper khác (bản hội nghị/journal hoặc trùng file)")
    counts: dict[str, int] = {}
    for res in results:
        counts[res["status"]] = counts.get(res["status"], 0) + 1
    publication: dict[str, int] = {}
    for res in results:
        publication[res["publication"]] = publication.get(res["publication"], 0) + 1
    return {"references": results, "counts": counts, "duplicates": len(duplicates), "publication": publication}
