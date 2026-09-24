"""Chunker cơ bản (Tuần 1)."""

import uuid

from app.core.schemas import Chunk
from app.pipeline.parser.pdf_parser import PageText

DEFAULT_CHUNK_SIZE = 800  # ký tự
DEFAULT_OVERLAP = 150


def chunk_pages(
    paper_id: str,
    pages: list[PageText],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Ghép text các trang rồi cắt theo cửa sổ trượt cố định (ký tự)."""
    full_text = ""
    page_boundaries: list[tuple[int, int]] = []
    for p in pages:
        page_boundaries.append((len(full_text), p.page))
        full_text += p.text

    chunks: list[Chunk] = []
    n = len(full_text)
    if n == 0:
        return chunks

    step = max(chunk_size - overlap, 1)
    start = 0
    index = 0
    while start < n:
        end = min(start + chunk_size, n)
        text = full_text[start:end].strip()
        if text:
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    paper_id=paper_id,
                    text=text,
                    chunk_index=index,
                    page=_page_for_offset(start, page_boundaries),
                    section=None,
                )
            )
            index += 1
        if end == n:
            break
        start += step
    return chunks


def _page_for_offset(offset: int, boundaries: list[tuple[int, int]]) -> int | None:
    page = None
    for start_char, page_number in boundaries:
        if start_char <= offset:
            page = page_number
        else:
            break
    return page
