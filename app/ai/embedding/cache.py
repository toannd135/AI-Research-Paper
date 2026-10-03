"""Cache embedding theo hash content, backed bởi Redis (share + persist qua nhiều Celery worker)."""

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


def get(text: str, model_name: str) -> list[float] | None:
    raw = _get_client().get(_key(text, model_name))
    return json.loads(raw) if raw is not None else None


def set(text: str, model_name: str, vector: list[float]) -> None:
    _get_client().set(_key(text, model_name), json.dumps(vector))


def clear() -> None:
    client = _get_client()
    keys = client.keys(_PREFIX + "*")
    if keys:
        client.delete(*keys)
