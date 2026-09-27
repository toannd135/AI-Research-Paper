"""Tool tìm kiếm bài báo khoa học từ nguồn học thuật bên ngoài (OpenAlex)."""

from __future__ import annotations

from app.ai.external.openalex_client import OpenAlexError, search_works
from app.ai.external.openalex_mapper import build_source_search_response
from app.core.schemas import SourceSearchResponse


def search_external_papers(query: str, count: int = 10) -> SourceSearchResponse:
    """Tìm kiếm các bài báo khoa học từ kho OpenAlex toàn cầu theo từ khóa hoặc chủ đề nghiên cứu.

    Trả về SourceSearchResponse gồm danh sách sources và relations (trích dẫn, liên quan).
    """
    if not query.strip():
        return SourceSearchResponse(sources=[], relations=[])
    try:
        raw_works = search_works(query=query, count=count)
    except OpenAlexError:
        return SourceSearchResponse(sources=[], relations=[])

    return build_source_search_response(raw_works)
