"""Cache embedding theo hash content."""

import hashlib

_cache: dict[str, list[float]] = {}


def _key(text: str, model_name: str) -> str:
    return hashlib.sha256(f"{model_name}:{text}".encode()).hexdigest()


def get(text: str, model_name: str) -> list[float] | None:
    return _cache.get(_key(text, model_name))


def set(text: str, model_name: str, vector: list[float]) -> None:
    _cache[_key(text, model_name)] = vector


def clear() -> None:
    _cache.clear()
