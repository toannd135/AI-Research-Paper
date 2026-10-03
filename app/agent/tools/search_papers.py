"""Tool tìm paper: hybrid search + rerank trên TOÀN BỘ kho paper đã ingest (không lọc paper_id)."""

from app.ai.retrieval.hybrid import search_hybrid
from app.ai.retrieval.reranker import rerank
from app.core.schemas import ScoredChunk


def search_papers(query: str, top_k: int = 6, candidate_k: int = 20) -> list[ScoredChunk]:
    """Trả về top_k chunk liên quan nhất tới `query`, quét trên toàn bộ paper trong Qdrant."""
    candidates = search_hybrid(query, top_k=candidate_k, paper_id=None)
    return rerank(query, candidates, top_k=top_k)


def _invoke_search_papers(input_dict: dict) -> list[ScoredChunk]:
    return search_papers(
        query=input_dict.get("query", ""),
        top_k=input_dict.get("top_k", 6),
        candidate_k=input_dict.get("candidate_k", 20),
    )


search_papers.invoke = _invoke_search_papers

