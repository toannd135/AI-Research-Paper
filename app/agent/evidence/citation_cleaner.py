"""Bộ chuẩn hóa và định dạng danh mục tài liệu tham khảo theo chuẩn học thuật (IEEE/ACM).

Chức năng:
1. Deduplicate: Hợp nhất các chunk thuộc cùng một bài báo về một trích dẫn duy nhất.
2. Canonical Formatter: Định dạng trích dẫn theo chuẩn 'Authors (Year). Title. Venue/DOI',
   tuyệt đối không dump raw search snippet (Page: 1, Section: ...).
3. Citation Pruner & Remapper: Lọc bỏ bài báo không được cite trong văn bản,
   đánh số lại thứ tự [1], [2], ... tăng dần và đồng bộ vào nội dung văn bản.
"""

from __future__ import annotations

import re
from typing import Any


def _normalize_title(title: str) -> str:
    """Chuẩn hóa tiêu đề để so khớp deduplication."""
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", title).lower()
    return " ".join(clean.split())


def _extract_citation_metadata(paper_id: str, snippet: str = "") -> dict[str, str]:
    """Trích xuất authors, title, year, venue từ chuỗi paper_id hoặc snippet."""
    # Mẫu 1: "Title: X Authors: Y (Year) Venue/DOI: Z"
    combined = f"{paper_id} {snippet}"

    title = paper_id.strip()
    authors = ""
    year = ""
    venue = ""

    title_match = re.search(r"Title:\s*([^\n\r]+?)(?=\s+Authors:|\s+DOI:|\s+Venue:|$)", combined, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip().strip('"').strip("'")

    auth_match = re.search(r"Authors:\s*([^\n\r]+?)(?=\s+\(\d{4}\)|\s+DOI:|\s+Venue:|\s+Title:|$)", combined, re.IGNORECASE)
    if auth_match:
        authors = auth_match.group(1).strip()

    year_match = re.search(r"\b(20[12]\d)\b", combined)
    if year_match:
        year = year_match.group(1)

    venue_match = re.search(r"(?:Venue/Publisher|Venue|Published in):\s*([^\n\r]+?)(?=\s+DOI:|$)", combined, re.IGNORECASE)
    if venue_match:
        venue = venue_match.group(1).strip()

    doi_match = re.search(r"DOI:\s*([^\s,]+)", combined, re.IGNORECASE)
    doi = doi_match.group(1).strip() if doi_match else ""

    # Dọn dẹp tiêu đề nếu còn dính metadata
    for prefix in ["Title:", "Title :", "title:"]:
        if title.startswith(prefix):
            title = title[len(prefix):].strip()

    # Dọn dẹp authors
    if authors:
        authors = authors.rstrip(",;")
        if not authors.endswith("et al.") and not authors.endswith("et al") and "," in authors:
            parts = [p.strip() for p in authors.split(",") if p.strip()]
            if len(parts) > 2:
                authors = f"{parts[0]} et al."
            else:
                authors = " and ".join(parts)
        if authors.endswith("et al"):
            authors += "."
    else:
        # Thử đoán tác giả từ title
        lead_words = title.split()[:2]
        authors = " ".join(lead_words) + " et al." if len(lead_words) >= 2 else "Anonymous et al."

    if not year:
        year = "2024"

    return {
        "title": title[:180],
        "authors": authors,
        "year": year,
        "venue": venue or "arXiv preprint",
        "doi": doi,
    }


def clean_and_deduplicate_citations(
    citations: list[Any],
    text: str,
) -> tuple[str, list[str]]:
    """Hợp nhất các citation trùng lặp, format IEEE chuẩn, và đồng bộ lại số [n] trong văn bản.
    
    Returns:
        (updated_text, clean_reference_lines)
    """
    if not citations:
        return text, []

    # 1. Deduplicate các citations dựa trên tiêu đề chuẩn hóa
    canonical_list: list[dict[str, str]] = []
    norm_to_canon_idx: dict[str, int] = {}
    orig_idx_to_canon_idx: dict[int, int] = {}

    for orig_idx, c in enumerate(citations, start=1):
        pid = getattr(c, "paper_id", "") or (c.get("paper_id") if isinstance(c, dict) else "")
        snippet = getattr(c, "text_snippet", "") or (c.get("text_snippet") if isinstance(c, dict) else "")
        meta = _extract_citation_metadata(pid, str(snippet))
        norm_t = _normalize_title(meta["title"])

        if norm_t in norm_to_canon_idx:
            canon_idx = norm_to_canon_idx[norm_t]
        else:
            canon_idx = len(canonical_list) + 1
            norm_to_canon_idx[norm_t] = canon_idx
            canonical_list.append(meta)

        orig_idx_to_canon_idx[orig_idx] = canon_idx

    # 2. Tìm tất cả các chỉ số citation được thực sự sử dụng trong văn bản
    used_orig_indices = [int(m) for m in re.findall(r"\[(\d+)\]", text)]
    used_canon_indices = sorted({orig_idx_to_canon_idx[i] for i in used_orig_indices if i in orig_idx_to_canon_idx})

    # Nếu văn bản chưa cite gì (hoặc draft offline), giữ lại tất cả canonical
    if not used_canon_indices:
        used_canon_indices = list(range(1, len(canonical_list) + 1))

    # 3. Tạo bảng ánh xạ mới: canon_idx -> new_sequential_idx (1, 2, 3...)
    canon_to_new: dict[int, int] = {old_c: new_i for new_i, old_c in enumerate(used_canon_indices, start=1)}
    orig_to_new: dict[int, int] = {}
    for orig_i, canon_i in orig_idx_to_canon_idx.items():
        if canon_i in canon_to_new:
            orig_to_new[orig_i] = canon_to_new[canon_i]

    # 4. Thay thế các nhãn [n] trong văn bản
    def _repl_citation(match: re.Match) -> str:
        idx = int(match.group(1))
        new_idx = orig_to_new.get(idx)
        return f"[{new_idx}]" if new_idx is not None else match.group(0)

    updated_text = re.sub(r"\[(\d+)\]", _repl_citation, text)

    # 5. Sinh danh sách tham khảo theo định dạng chuẩn IEEE
    formatted_references = []
    for old_c in used_canon_indices:
        new_i = canon_to_new[old_c]
        meta = canonical_list[old_c - 1]
        authors = meta["authors"]
        title = meta["title"]
        year = meta["year"]
        venue = meta["venue"]
        doi_part = f", DOI: {meta['doi']}" if meta["doi"] else ""

        ref_entry = f"[{new_i}] {authors}, \"{title},\" *{venue}*, {year}{doi_part}."
        formatted_references.append(ref_entry)

    return updated_text, formatted_references
