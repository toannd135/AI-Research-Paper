"""Tìm kiếm vector trên Qdrant."""

from app.ai.embedding.service import embed_query
from app.core.schemas import Chunk, ScoredChunk
from app.pipeline.vector_store.qdrant_client import search as qdrant_search


def search_vector(query: str, top_k: int = 10, paper_id: str | None = None) -> list[ScoredChunk]:
    """Embed câu hỏi rồi tìm các chunk gần nhất trong Qdrant."""
    query_vector = embed_query(query)
    points = qdrant_search(query_vector, top_k=top_k, paper_id=paper_id)
    return [_to_scored_chunk(point) for point in points]


def _to_scored_chunk(point) -> ScoredChunk:
    payload = point.payload or {}
    chunk = Chunk(
        id=str(point.id),
        paper_id=payload.get("paper_id", ""),
        text=payload.get("text", ""),
        chunk_index=payload.get("chunk_index", 0),
        page=payload.get("page"),
        section=payload.get("section"),
    )
    return ScoredChunk(chunk=chunk, score=point.score)
