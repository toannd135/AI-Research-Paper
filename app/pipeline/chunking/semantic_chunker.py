"""Chunker section/paragraph-aware (Tuần 2)."""

import re
import uuid

from app.core.schemas import Chunk
from app.pipeline.parser.pdf_parser import PageText
from app.pipeline.parser.section_detector import assign_section, detect_sections

DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 150

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def chunk_pages(
    paper_id: str,
    pages: list[PageText],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Gộp các đoạn văn liên tiếp trong từng trang tới gần chunk_size, gắn kèm section gần nhất."""
    sections = detect_sections(pages)
    chunks: list[Chunk] = []
    index = 0

    for page in pages:
        paragraphs = [p for p in _PARAGRAPH_SPLIT.split(page.text) if p.strip()]
        buffer = ""
        buffer_offset = 0
        search_from = 0

        for para in paragraphs:
            para_offset = page.text.find(para, search_from)
            if para_offset == -1:
                para_offset = search_from
            search_from = para_offset + len(para)

            if buffer and len(buffer) + len(para) > chunk_size:
                section = assign_section(page.page, buffer_offset, sections)
                chunks.append(_make_chunk(paper_id, buffer, index, page.page, section))
                index += 1
                tail = buffer[-overlap:] if overlap else ""
                buffer = f"{tail}\n\n{para}".strip()
                buffer_offset = para_offset
            else:
                if not buffer:
                    buffer_offset = para_offset
                buffer = f"{buffer}\n\n{para}".strip() if buffer else para

        if buffer.strip():
            section = assign_section(page.page, buffer_offset, sections)
            chunks.append(_make_chunk(paper_id, buffer, index, page.page, section))
            index += 1

    return chunks


def _make_chunk(paper_id: str, text: str, index: int, page: int, section: str | None) -> Chunk:
    return Chunk(
        id=str(uuid.uuid4()),
        paper_id=paper_id,
        text=text.strip(),
        chunk_index=index,
        page=page,
        section=section,
    )
