"""PyMuPDF / Docling wrapper."""

from dataclasses import dataclass

import pymupdf


@dataclass
class PageText:
    page: int
    text: str


def parse_pdf(file_path: str) -> list[PageText]:
    """Trích xuất text theo từng trang từ file PDF."""
    pages: list[PageText] = []
    with pymupdf.open(file_path) as doc:
        for i, page in enumerate(doc, start=1):
            pages.append(PageText(page=i, text=page.get_text("text")))
    return pages
