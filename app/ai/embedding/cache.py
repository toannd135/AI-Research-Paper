"""Cache embedding theo hash content, backed bởi Redis (share + persist qua nhiều Celery worker).

TTL đọc từ EMBEDDING_CACHE_TTL_SECONDS (0 = không hết hạn) để cache không phình vô hạn khi
re-ingest nhiều paper; get_many() dùng MGET để 1 batch chunk chỉ tốn 1 round-trip Redis.
"""

import hashlib
import json

import redis

from app.core.config import get_settings

_PREFIX = "embcache:"
_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().redis_url)
    return _client


def _key(text: str, model_name: str) -> str:
    return _PREFIX + hashlib.sha256(f"{model_name}:{text}".encode()).hexdigest()


def _ttl() -> int | None:
    ttl = get_settings().embedding_cache_ttl_seconds
    return ttl if ttl and ttl > 0 else None


def get(text: str, model_name: str) -> list[float] | None:
    raw = _get_client().get(_key(text, model_name))
    return json.loads(raw) if raw is not None else None


def get_many(texts: list[str], model_name: str) -> list[list[float] | None]:
    """Lấy nhiều vector trong 1 lần MGET; phần tử None = cache miss."""
    if not texts:
        return []
    raws = _get_client().mget([_key(t, model_name) for t in texts])
    return [json.loads(raw) if raw is not None else None for raw in raws]


def set(text: str, model_name: str, vector: list[float]) -> None:
    _get_client().set(_key(text, model_name), json.dumps(vector), ex=_ttl())


def set_many(items: list[tuple[str, list[float]]], model_name: str) -> None:
    """Ghi nhiều vector bằng pipeline (1 round-trip)."""
    if not items:
        return
    ttl = _ttl()
    pipe = _get_client().pipeline(transaction=False)
    for text, vector in items:
        pipe.set(_key(text, model_name), json.dumps(vector), ex=ttl)
    pipe.execute()


def clear() -> None:
    client = _get_client()
    keys = list(client.scan_iter(match=_PREFIX + "*", count=1000))
    if keys:
        client.delete(*keys)
