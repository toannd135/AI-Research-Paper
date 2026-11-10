"""Metadata thư mục của PDF người dùng tải lên: chỉ lấy điều đọc được từ chính file, thiếu thì để trống (không đoán)."""

import logging
import re
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
_YEAR_RE = re.compile(r"(?:©|\(c\)|copyright|published(?:\s+online)?)[^\d\n]{0,40}((?:19|20)\d{2})", re.IGNORECASE)
_ARXIV_RE = re.compile(r"arXiv:(\d{2})(?:0[1-9]|1[0-2])\.\d{4,5}", re.IGNORECASE)
_JUNK_TITLE_RE = re.compile(r"^(?:untitled|microsoft word\b)|\.(?:pdf|docx?|tex|dvi|indd)$", re.IGNORECASE)
_MIN_TITLE_WORDS = 3
_MAX_TITLE_CHARS = 250


def _valid_title(text: str) -> bool:
    return len(text.split()) >= _MIN_TITLE_WORDS and len(text) <= _MAX_TITLE_CHARS and not _JUNK_TITLE_RE.search(text)


def _title_from_layout(page: pymupdf.Page) -> str:
    """Các dòng cỡ chữ lớn nhất ở nửa trên trang đầu."""
    lines: list[tuple[float, str]] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = " ".join(s["text"].strip() for s in line["spans"]).strip()
            if text and line["bbox"][1] < page.rect.height / 2 and not text.lower().startswith("arxiv:"):
                lines.append((max(s["size"] for s in line["spans"]), text))
    if not lines:
        return ""
    largest = max(size for size, _ in lines)
    return " ".join(" ".join(text for size, text in lines if size >= largest - 0.5).split())


def _publication_year(text: str) -> str:
    """Năm chỉ lấy khi trang đầu ghi rõ; ngày tạo file PDF không phải năm xuất bản."""
    if match := _YEAR_RE.search(text):
        return match.group(1)
    if match := _ARXIV_RE.search(text):
        return f"20{match.group(1)}"
    return ""


def extract_paper_metadata(file_path: str, filename: str) -> dict[str, str]:
    """Trả về title/authors/year/venue/doi; title luôn có (tệ nhất là tên file), các trường khác có thể rỗng."""
    meta = {"title": Path(filename).stem.replace("_", " ").strip() or filename, "authors": "", "year": "", "venue": "", "doi": ""}
    try:
        with pymupdf.open(file_path) as doc:
            info = doc.metadata or {}
            page = doc[0]
            first_page = page.get_text("text")
            layout_title = _title_from_layout(page)
    except (OSError, RuntimeError, ValueError, IndexError):
        logger.warning("Không đọc được metadata của %s; dùng tên file làm tiêu đề", file_path, exc_info=True)
        return meta

    embedded_title = " ".join((info.get("title") or "").split())
    meta["title"] = next((t for t in (embedded_title, layout_title) if _valid_title(t)), meta["title"])
    authors = (info.get("author") or "").strip()
    # Một từ đơn thường là tài khoản máy tính ("admin", "user"), không phải tác giả.
    meta["authors"] = authors if len(authors.replace(",", " ").split()) >= 2 else ""
    meta["year"] = _publication_year(first_page)
    if match := _DOI_RE.search(first_page):
        meta["doi"] = match.group(0).rstrip(".,;)")
    return meta
