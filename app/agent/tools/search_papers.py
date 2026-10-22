"""Tool tìm paper: hybrid search + rerank trên TOÀN BỘ kho paper đã ingest (không lọc paper_id)."""

from app.ai.retrieval.hybrid import search_hybrid
from app.ai.retrieval.reranker import rerank
from app.core.schemas import ScoredChunk
from app.core.scope import filter_chunks, get_allowed_paper_ids


def search_papers(query: str, top_k: int = 6, candidate_k: int = 20) -> list[ScoredChunk]:
    """Trả về top_k chunk liên quan nhất tới `query`, quét trên toàn bộ paper trong Qdrant."""
    # Truy xuất toàn cục rồi lọc theo chủ sở hữu của phiên nghiên cứu (không để lộ paper của người khác).
    candidates = filter_chunks(search_hybrid(query, top_k=candidate_k * 3, paper_id=None), get_allowed_paper_ids())[:candidate_k]
    return rerank(query, candidates, top_k=top_k)


def _invoke_search_papers(input_dict: dict) -> list[ScoredChunk]:
    return search_papers(
        query=input_dict.get("query", ""),
        top_k=input_dict.get("top_k", 6),
        candidate_k=input_dict.get("candidate_k", 20),
    )


search_papers.invoke = _invoke_search_papers

