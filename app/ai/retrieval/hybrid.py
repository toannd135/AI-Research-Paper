"""Kết hợp vector + BM25 theo alpha/beta."""

from app.ai.retrieval.bm25_search import search_bm25
from app.ai.retrieval.vector_search import search_vector
from app.core.config import get_settings
from app.core.schemas import ScoredChunk


def _normalize(scored: list[ScoredChunk]) -> dict[str, float]:
    if not scored:
        return {}
    scores = [s.score for s in scored]
    lo, hi = min(scores), max(scores)
    span = hi - lo
    if span == 0:
        return {s.chunk.id: 1.0 for s in scored}
    return {s.chunk.id: (s.score - lo) / span for s in scored}


def search_hybrid(query: str, top_k: int = 10, paper_id: str | None = None) -> list[ScoredChunk]:
    """Kết hợp điểm vector + BM25 (min-max normalize) theo HYBRID_ALPHA/HYBRID_BETA."""
    settings = get_settings()
    vector_results = search_vector(query, top_k=top_k * 2, paper_id=paper_id)
    bm25_results = search_bm25(query, top_k=top_k * 2, paper_id=paper_id)

    vector_norm = _normalize(vector_results)
    bm25_norm = _normalize(bm25_results)

    chunks_by_id = {s.chunk.id: s.chunk for s in vector_results}
    chunks_by_id.update({s.chunk.id: s.chunk for s in bm25_results})

    combined = [
        ScoredChunk(
            chunk=chunk,
            score=settings.hybrid_alpha * vector_norm.get(chunk_id, 0.0)
            + settings.hybrid_beta * bm25_norm.get(chunk_id, 0.0),
        )
        for chunk_id, chunk in chunks_by_id.items()
    ]
    combined.sort(key=lambda s: s.score, reverse=True)
    return combined[:top_k]
