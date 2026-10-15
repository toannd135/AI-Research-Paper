"""BGE-Reranker / cross-encoder."""

import logging
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.ai.device import load_with_fallback, resolve_device, run_with_oom_fallback
from app.core.config import get_settings
from app.core.schemas import ScoredChunk

logger = logging.getLogger(__name__)


@lru_cache
def _load_model() -> CrossEncoder:
    settings = get_settings()
    # Reranker nạp SAU embedding nên VRAM còn lại đã hụt đi phần của BGE-M3; resolve_device()
    # đo lại bộ nhớ trống tại thời điểm này nên có thể chọn CPU dù embedding đang ở GPU.
    device = resolve_device(settings.embedding_device)
    model, used = load_with_fallback(
        lambda d: CrossEncoder(settings.reranker_model, device=d), device, "Reranker"
    )
    logger.info("Đã nạp reranker %s trên %s", settings.reranker_model, used)
    return model


def rerank(query: str, candidates: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
    """Rerank lại danh sách candidate bằng cross-encoder, trả về top_k theo điểm mới."""
    if not candidates:
        return []

    pairs = [(query, c.chunk.text) for c in candidates]
    scores = run_with_oom_fallback(
        lambda: _load_model().predict(pairs), on_oom=_load_model.cache_clear, label="Reranker"
    )

    reranked = [
        ScoredChunk(chunk=c.chunk, score=float(score)) for c, score in zip(candidates, scores, strict=True)
    ]
    reranked.sort(key=lambda s: s.score, reverse=True)
    return reranked[:top_k]
