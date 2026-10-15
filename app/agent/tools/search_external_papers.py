"""Tool tìm kiếm bài báo khoa học từ nguồn học thuật bên ngoài (OpenAlex)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.ai.external.openalex_client import search_works
from app.ai.external.openalex_mapper import build_source_search_response
from app.core.schemas import Chunk, ExternalSource, ScoredChunk, SourceSearchResponse


def search_external_papers(query: str, count: int = 10) -> SourceSearchResponse:
    """Tìm kiếm các bài báo khoa học từ kho OpenAlex toàn cầu theo từ khóa hoặc chủ đề nghiên cứu.

    Trả về SourceSearchResponse gồm danh sách sources và relations (trích dẫn, liên quan).
    """
    if not query.strip():
        return SourceSearchResponse(sources=[], relations=[])
    try:
        raw_works = search_works(query=query, count=count)
    except Exception:
        return SourceSearchResponse(sources=[], relations=[])

    return build_source_search_response(raw_works)


def external_source_to_scored_chunk(source: ExternalSource, index: int = 0) -> ScoredChunk:
    """Chuyển đổi một ExternalSource từ OpenAlex thành ScoredChunk tương thích chuẩn RAG."""
    text_parts = [
        f"Title: {source.title}",
        f"Authors: {source.authors} ({source.year})",
    ]
    if source.doi:
        text_parts.append(f"DOI: {source.doi}")
    if source.publisher:
        text_parts.append(f"Venue/Publisher: {source.publisher}")
    if source.type:
        text_parts.append(f"Publication Type: {source.type}")
    if source.citations:
        text_parts.append(f"Citations: {source.citations}")
    if source.abstract:
        text_parts.append(f"Abstract:\n{source.abstract}")
    else:
        text_parts.append("Abstract: Không có bản tóm tắt chi tiết từ nguồn OpenAlex.")

    full_text = "\n".join(text_parts)
    paper_title = source.title[:100] if source.title else f"OpenAlex_{source.id}"
    score = float(source.relevance) / 100.0 if source.relevance else 0.85

    chunk = Chunk(
        id=f"openalex_{source.id}",
        paper_id=paper_title,
        text=full_text,
        chunk_index=index,
        page=1,
        section="Abstract & Literature Overview",
        score=score,
    )
    return ScoredChunk(chunk=chunk, score=score)


def retrieve_external_evidence(queries: list[str], count_per_query: int = 8, max_total: int = 30) -> list[ScoredChunk]:
    """Tìm tài liệu học thuật từ OpenAlex cho danh sách sub-query (song song, vì mỗi query là 1 HTTP
    request độc lập) và chuyển thành ScoredChunk; dedup theo source.id, giữ thứ tự query ưu tiên."""
    clean_queries = [q.strip() for q in queries if q and q.strip()]
    if not clean_queries:
        return []

    def _search(q: str) -> list[ExternalSource]:
        try:
            return search_external_papers(q, count=count_per_query).sources
        except Exception:  # 1 query lỗi không được làm hỏng cả vòng tìm kiếm
            return []

    with ThreadPoolExecutor(max_workers=min(len(clean_queries), 5)) as pool:
        results_per_query = list(pool.map(_search, clean_queries))

    collected: dict[str, ScoredChunk] = {}
    for sources in results_per_query:
        for idx, src in enumerate(sources):
            if src.id not in collected:
                collected[src.id] = external_source_to_scored_chunk(src, index=idx)
            if len(collected) >= max_total:
                break
        if len(collected) >= max_total:
            break

    return sorted(collected.values(), key=lambda s: s.score, reverse=True)
