"""Unit test cho embedding cache (Redis-backed) dùng fake client, không cần Redis thật chạy."""

from app.ai.embedding import cache


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self.last_ttl: int | None = None

    def get(self, key: str):
        return self._store.get(key)

    def mget(self, keys: list[str]):
        return [self._store.get(k) for k in keys]

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value
        self.last_ttl = ex

    def scan_iter(self, match: str, count: int = 1000):
        prefix = match.rstrip("*")
        return iter([k for k in self._store if k.startswith(prefix)])

    def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)

    def pipeline(self, transaction: bool = False):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, str, int | None]] = []

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._ops.append((key, value, ex))

    def execute(self) -> None:
        for key, value, ex in self._ops:
            self._redis.set(key, value, ex=ex)


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


def test_get_many_and_set_many_round_trip(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "_get_client", lambda: fake)

    cache.set_many([("a", [1.0]), ("b", [2.0])], "model-a")

    assert cache.get_many(["a", "missing", "b"], "model-a") == [[1.0], None, [2.0]]
    assert cache.get_many([], "model-a") == []


def test_set_applies_ttl_from_settings(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "_get_client", lambda: fake)
    monkeypatch.setattr(cache, "_ttl", lambda: 123)

    cache.set("hello", "model-a", [1.0])

    assert fake.last_ttl == 123
