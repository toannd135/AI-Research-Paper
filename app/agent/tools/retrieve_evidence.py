"""Tool gọi vào app/ai/retrieval cho nhiều sub-query, gộp + dedup thành 1 pool evidence."""

from concurrent.futures import ThreadPoolExecutor
from functools import partial

from app.agent.tools.search_papers import search_papers
from app.core.schemas import ScoredChunk


def retrieve_evidence(queries: list[str], top_k_per_query: int = 6) -> list[ScoredChunk]:
    """Chạy search_papers cho từng sub-query SONG SONG (mỗi sub-query độc lập với nhau — mỗi cái
    tự làm hybrid search + rerank riêng), dedup theo chunk.id (giữ điểm cao nhất), sort theo score
    giảm dần. plan_node thường sinh 3-5 sub-query; chạy tuần tự trước đây nhân latency của 1 lần
    search_papers lên 3-5 lần cho mỗi request nghiên cứu.
    """
    if not queries:
        return []

    search = partial(search_papers, top_k=top_k_per_query)
    with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as executor:
        results_per_query = list(executor.map(search, queries))

    best_by_id: dict[str, ScoredChunk] = {}
    for results in results_per_query:
        for scored in results:
            existing = best_by_id.get(scored.chunk.id)
            if existing is None or scored.score > existing.score:
                best_by_id[scored.chunk.id] = scored

    return sorted(best_by_id.values(), key=lambda s: s.score, reverse=True)
