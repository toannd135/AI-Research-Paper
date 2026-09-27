"""embed_batch(), load model BGE-M3 / OpenAI."""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.ai.embedding import cache
from app.core.config import get_settings


@lru_cache
def _load_model() -> SentenceTransformer:
    # Chạy CPU: tránh phụ thuộc VRAM GPU (có thể bị chiếm bởi process khác hoặc không đủ
    # cho cả embedding + reranker cùng lúc).
    return SentenceTransformer(get_settings().embedding_model, device="cpu")


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Trả về vector embedding cho từng text, dùng cache theo hash content trước khi gọi model."""
    model_name = get_settings().embedding_model

    results: list[list[float] | None] = [cache.get(t, model_name) for t in texts]
    missing_indices = [i for i, r in enumerate(results) if r is None]

    if missing_indices:
        model = _load_model()
        missing_texts = [texts[i] for i in missing_indices]
        vectors = model.encode(missing_texts, normalize_embeddings=True).tolist()
        for idx, vector in zip(missing_indices, vectors, strict=True):
            cache.set(texts[idx], model_name, vector)
            results[idx] = vector

    return results  # type: ignore[return-value]


def embed_query(text: str) -> list[float]:
    return embed_batch([text])[0]
