"""Unit test cho embedding cache (Redis-backed) dùng fake client, không cần Redis thật chạy."""

from app.ai.embedding import cache


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value

    def keys(self, pattern: str):
        prefix = pattern.rstrip("*")
        return [k for k in self._store if k.startswith(prefix)]

    def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)


def test_get_returns_none_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(cache, "_get_client", lambda: _FakeRedis())
    assert cache.get("hello", "model-a") is None


def test_set_then_get_round_trip(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "_get_client", lambda: fake)

    cache.set("hello", "model-a", [0.1, 0.2, 0.3])

    assert cache.get("hello", "model-a") == [0.1, 0.2, 0.3]


def test_different_model_name_is_different_key(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "_get_client", lambda: fake)

    cache.set("hello", "model-a", [1.0])

    assert cache.get("hello", "model-b") is None


def test_clear_removes_only_embcache_keys(monkeypatch) -> None:
    fake = _FakeRedis()
    fake.set("unrelated:key", "keep-me")
    monkeypatch.setattr(cache, "_get_client", lambda: fake)

    cache.set("hello", "model-a", [1.0])
    cache.clear()

    assert cache.get("hello", "model-a") is None
    assert fake.get("unrelated:key") == "keep-me"
