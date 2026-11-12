"""Metadata trích dẫn (tiêu đề, tác giả, năm, venue) đọc thẳng từ PDF đã upload.

Dùng khi paper không có trong catalog.json (vd. kho upload qua giao diện: id là UUID mới) — trước đây
reference khi đó lấy luôn UUID làm tiêu đề và 'Anonymous' làm tác giả. Thứ tự ưu tiên:
metadata nhúng trong PDF (nếu hợp lệ) → chữ cỡ lớn nhất ở nửa trên trang 1 → tên tệp gốc.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_BAD_META_TITLE_RE = re.compile(
    r"^(untitled|microsoft|word|doi|arxiv|paper|article|manuscript|title|main|template|sample|\S+\.(pdf|docx?|tex|dvi))\b"
    r"|^[\d\s._-]+$|^[0-9a-f-]{20,}$",
    re.I,
)
_BAD_META_AUTHOR_RE = re.compile(r"^(author|admin|administrator|user|owner|unknown|ieee|elsevier|springer|acm)\b", re.I)
_ARXIV_RE = re.compile(r"arXiv:\s*(\d{2})(\d{2})\.(\d{4,5})", re.I)
_VENUE_RE = re.compile(
    r"(IEEE Transactions on [A-Z][\w ,&-]+?|IEEE/CVF [A-Za-z ]+Conference[\w ()]*|Proceedings of the [\w ,()&-]+?"
    r"|IEEE Access|Pattern Recognition|Neurocomputing|Information Fusion|Applied Sciences|Sensors|Electronics"
    r"|Scientific Reports|Expert Systems with Applications|Neural Networks|ACM Computing Surveys"
    r"|(?:CVPR|ICCV|ECCV|NeurIPS|ICLR|ICML|AAAI|IJCAI|ACM MM|ICASSP|INTERSPEECH|WACV|BMVC)\s*(?:20\d{2}|'\d{2})?)"
    r"(?=[\s,.;:)\d]|$)"
)
_NAME_RE = re.compile(r"^[A-Z][A-Za-zÀ-ɏ'.-]+(?:\s+[A-Z]\.?)*(?:\s+[A-Za-zÀ-ɏ'.-]+){0,3}$")
_NON_NAME_RE = re.compile(
    r"\b(abstract|university|institute|department|school|college|laboratory|lab|center|centre|inc|ltd|corresponding|email|"
    r"received|accepted|published|journal|conference|vol|keywords|introduction|ieee|member|senior|fellow|student)\b",
    re.I,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _plausible_title(title: str) -> bool:
    t = _clean(title)
    return 12 <= len(t) <= 250 and len(t.split()) >= 3 and not _BAD_META_TITLE_RE.search(t) and not _UUID_RE.match(t)


def _title_from_filename(filename: str) -> str:
    stem = Path(filename or "").stem
    if not stem or _UUID_RE.match(stem):
        return ""
    title = _clean(re.sub(r"[_]+", " ", stem))
    return title if len(title.split()) >= 2 else ""


def _split_names(line: str) -> list[str]:
    line = re.sub(r"[\d*†‡§¶∗,]+(?=\s*(?:,|and\b|&|$))", "", line)  # dấu chú thích sau tên
    line = re.sub(r"[*†‡§¶∗]", "", line)
    parts = [p.strip(" .") for p in re.split(r",|;|\band\b|&|·", line) if p.strip(" .")]
    return [p for p in parts if _NAME_RE.match(p) and len(p.split()) >= 2]


def _line_text(line: dict) -> tuple[str, float]:
    """Chữ của một dòng (rawdict), chèn dấu cách theo khoảng trống giữa các ký tự — nhiều PDF không lưu ký tự cách."""
    out, prev_x1, size = [], None, 0.0
    for span in line.get("spans", []):
        chars = span.get("chars", [])
        if not "".join(c["c"] for c in chars).strip():
            continue
        size = max(size, span["size"])
        for c in chars:
            ch, (x0, _, x1, _) = c["c"], c["bbox"]
            if prev_x1 is not None and x0 - prev_x1 > span["size"] * 0.18 and out and out[-1] != " " and ch != " ":
                out.append(" ")
            out.append(ch)
            prev_x1 = x1
    return _clean("".join(out)), size


def _first_page_fields(page) -> tuple[str, list[str]]:
    """(tiêu đề, tác giả) từ trang 1: tiêu đề = các dòng cỡ chữ lớn nhất ở nửa trên; tác giả = dòng tên ngay sau tiêu đề."""
    lines: list[tuple[float, float, str]] = []  # (y, size, text)
    for block in page.get_text("rawdict").get("blocks", []):
        for line in block.get("lines", []):
            text, size = _line_text(line)
            if text:
                lines.append((line["bbox"][1], size, text))
    top = [ln for ln in lines if ln[0] < page.rect.height * 0.5 and len(ln[2]) >= 2]
    if not top:
        return "", []
    sizes = sorted({round(ln[1], 1) for ln in top if len(ln[2]) >= 8}, reverse=True)
    title, title_end = "", -1.0
    for size in sizes[:3]:
        chunk = sorted((ln for ln in top if abs(ln[1] - size) < 0.6), key=lambda ln: ln[0])
        # các dòng liền nhau (khoảng cách < 2.2 lần cỡ chữ) tạo thành khối tiêu đề
        block = [chunk[0]]
        for ln in chunk[1:]:
            if ln[0] - block[-1][0] > size * 2.2:
                break
            block.append(ln)
        candidate = _clean(" ".join(ln[2] for ln in block))
        looks_like_authors = candidate.count(",") >= 3 or re.search(r"\b(member|fellow),? ieee\b", candidate, re.I)
        if _plausible_title(candidate) and not looks_like_authors and not re.match(r"^(abstract|contents|received)\b", candidate, re.I):
            title, title_end = candidate, block[-1][0]
            break
    authors: list[str] = []
    if title:
        after = sorted((ln for ln in lines if ln[0] > title_end), key=lambda ln: ln[0])[:6]
        for _, _, text in after:
            if _NON_NAME_RE.search(text) or "@" in text:
                if authors:
                    break
                continue
            names = _split_names(text)
            if names:
                authors.extend(names)
            elif authors:
                break
    return title, authors[:12]


def _year(meta: dict, text: str) -> str:
    m = _ARXIV_RE.search(text)
    if m:
        return f"20{m.group(1)}"
    # năm của chính bài >= năm các công trình nó trích ở trang 1 (©, Received/Published, hội nghị…) → lấy năm lớn nhất hợp lệ
    from datetime import date

    years = [int(y) for y in re.findall(r"(?<!\d)((?:19[89]|20[0-4])\d)(?!\d)", text) if int(y) <= date.today().year]
    if years:
        return str(max(years))
    cd = re.search(r"D:(\d{4})", str(meta.get("creationDate") or ""))
    return cd.group(1) if cd else ""


def _venue(text: str) -> str:
    m = _ARXIV_RE.search(text)
    if m:
        return f"arXiv:{m.group(1)}{m.group(2)}.{m.group(3)}"
    head = text[:900]  # chỉ phần đầu trang 1 (khối trích dẫn/tiêu đề); xa hơn là tên tạp chí được trích dẫn trong bài
    if re.search(r"\bAppl\.\s*Sci\.", head):
        return "Applied Sciences"
    v = _VENUE_RE.search(head)
    return _clean(v.group(1)).rstrip(",;.") if v else ""


@lru_cache(maxsize=1024)
def _read_pdf(path: str, mtime: float) -> dict[str, str]:
    import pymupdf

    with pymupdf.open(path) as doc:
        meta = doc.metadata or {}
        page = doc[0] if doc.page_count else None
        text = page.get_text("text") if page is not None else ""
        title, authors = _first_page_fields(page) if page is not None else ("", [])
    meta_title = _clean(meta.get("title", ""))
    if _plausible_title(meta_title):
        title = meta_title
    meta_author = _clean(meta.get("author", ""))
    if meta_author and not _BAD_META_AUTHOR_RE.match(meta_author):
        names = [a for a in (_clean(x) for x in re.split(r";|,|\band\b", meta_author)) if len(a.split()) >= 2]
        if names:
            authors = names
    return {"title": title, "authors": ", ".join(authors), "year": _year(meta, text[:6000]), "venue": _venue(text[:6000])}


def pdf_citation_metadata(file_path: str, filename: str = "") -> dict[str, str]:
    """{title, authors (cách nhau dấu phẩy), year, venue, doi} của một PDF; trường không đọc được để rỗng."""
    meta = {"title": "", "authors": "", "year": "", "venue": "", "doi": ""}
    path = Path(file_path or "")
    if path.is_file():
        try:
            meta.update(_read_pdf(str(path), path.stat().st_mtime))
        except Exception:
            logger.warning("Không đọc được metadata PDF %s", path, exc_info=True)
    if not meta["title"]:
        meta["title"] = _title_from_filename(filename) or _title_from_filename(path.name)
    return meta
