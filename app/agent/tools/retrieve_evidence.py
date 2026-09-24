"""Tool gọi vào app/ai/retrieval cho nhiều sub-query, gộp + dedup thành 1 pool evidence."""

from app.agent.tools.search_papers import search_papers
from app.core.schemas import ScoredChunk


def retrieve_evidence(queries: list[str], top_k_per_query: int = 6) -> list[ScoredChunk]:
    """Chạy search_papers cho từng query, dedup theo chunk.id (giữ điểm cao nhất), sort theo score giảm dần."""
    best_by_id: dict[str, ScoredChunk] = {}
    for query in queries:
        for scored in search_papers(query, top_k=top_k_per_query):
            existing = best_by_id.get(scored.chunk.id)
            if existing is None or scored.score > existing.score:
                best_by_id[scored.chunk.id] = scored

    return sorted(best_by_id.values(), key=lambda s: s.score, reverse=True)
