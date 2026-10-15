"""embed_batch(): BGE-M3 qua sentence-transformers, cache Redis theo hash nội dung."""

import logging
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.ai.device import load_with_fallback, resolve_device, run_with_oom_fallback
from app.ai.embedding import cache
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_ENCODE_BATCH_SIZE = 16


@lru_cache
def _load_model() -> SentenceTransformer:
    settings = get_settings()
    device = resolve_device(settings.embedding_device)
    model, used = load_with_fallback(
        lambda d: SentenceTransformer(settings.embedding_model, device=d), device, "Embedding model"
    )
    logger.info("Đã nạp embedding model %s trên %s", settings.embedding_model, used)
    return model


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Trả về vector embedding cho từng text; chỉ gọi model cho các text chưa có trong cache."""
    if not texts:
        return []
    model_name = get_settings().embedding_model

    results: list[list[float] | None] = cache.get_many(texts, model_name)
    missing_indices = [i for i, r in enumerate(results) if r is None]

    if missing_indices:
        missing_texts = [texts[i] for i in missing_indices]

        def _encode() -> list[list[float]]:
            return _load_model().encode(
                missing_texts,
                normalize_embeddings=True,
                batch_size=_ENCODE_BATCH_SIZE,
                show_progress_bar=False,
            ).tolist()

        vectors = run_with_oom_fallback(_encode, on_oom=_load_model.cache_clear, label="Embedding")
        for idx, vector in zip(missing_indices, vectors, strict=True):
            results[idx] = vector
        cache.set_many(list(zip(missing_texts, vectors, strict=True)), model_name)

    return results  # type: ignore[return-value]


def embed_query(text: str) -> list[float]:
    return embed_batch([text])[0]
