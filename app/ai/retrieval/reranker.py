"""BGE-Reranker / cross-encoder."""

from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.core.config import get_settings
from app.core.schemas import ScoredChunk


@lru_cache
def _load_model() -> CrossEncoder:
    # Chạy CPU: tránh phụ thuộc VRAM GPU (có thể bị chiếm bởi process khác hoặc không đủ
    # cho cả embedding + reranker cùng lúc).
    return CrossEncoder(get_settings().reranker_model, device="cpu")


def rerank(query: str, candidates: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
    """Rerank lại danh sách candidate bằng cross-encoder, trả về top_k theo điểm mới."""
    if not candidates:
        return []

    model = _load_model()
    pairs = [(query, c.chunk.text) for c in candidates]
    scores = model.predict(pairs)

    reranked = [
        ScoredChunk(chunk=c.chunk, score=float(score)) for c, score in zip(candidates, scores, strict=True)
    ]
    reranked.sort(key=lambda s: s.score, reverse=True)
    return reranked[:top_k]
