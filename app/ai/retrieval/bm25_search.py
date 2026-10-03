"""Tìm kiếm từ khoá BM25."""

import re

from qdrant_client.http import models as qmodels
from rank_bm25 import BM25Okapi

from app.ai.retrieval import bm25_index_cache
from app.core.config import get_settings
from app.core.schemas import Chunk, ScoredChunk
from app.pipeline.vector_store.qdrant_client import get_client

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _load_corpus(paper_id: str | None) -> list[Chunk]:
    """Scroll toàn bộ chunk (theo paper_id nếu có) từ Qdrant để build BM25 index tạm thời cho mỗi query."""
    client = get_client()
    collection = get_settings().qdrant_collection
    if not client.collection_exists(collection):
        return []
    query_filter = None
    if paper_id:
        query_filter = qmodels.Filter(
            must=[qmodels.FieldCondition(key="paper_id", match=qmodels.MatchValue(value=paper_id))]
        )

    chunks: list[Chunk] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=query_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            chunks.append(
                Chunk(
                    id=str(point.id),
                    paper_id=payload.get("paper_id", ""),
                    text=payload.get("text", ""),
                    chunk_index=payload.get("chunk_index", 0),
                    page=payload.get("page"),
                    section=payload.get("section"),
                )
            )
        if offset is None:
            break
    return chunks


def search_bm25(query: str, top_k: int = 10, paper_id: str | None = None) -> list[ScoredChunk]:
    """BM25 keyword search trên chunk hiện có trong Qdrant.

    Index được cache theo scope (paper_id / toàn corpus) qua bm25_index_cache thay vì scroll +
    build lại BM25Okapi ở mỗi lần gọi — xem docstring của bm25_index_cache.py để biết lý do.
    """
    cached = bm25_index_cache.get(paper_id)
    if cached is not None:
        bm25, corpus = cached
    else:
        corpus = _load_corpus(paper_id)
        if not corpus:
            return []
        bm25 = BM25Okapi([_tokenize(c.text) for c in corpus])
        bm25_index_cache.set(paper_id, bm25, corpus)

    scores = bm25.get_scores(_tokenize(query))

    ranked = sorted(zip(corpus, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    return [ScoredChunk(chunk=c, score=float(s)) for c, s in ranked[:top_k] if s > 0]
