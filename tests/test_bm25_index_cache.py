"""Unit test cho bm25_index_cache: get/set/invalidate/TTL, không cần Qdrant/Redis thật."""

import time

from app.ai.retrieval import bm25_index_cache as cache


def setup_function() -> None:
    cache.clear()


def test_miss_returns_none() -> None:
    assert cache.get("unknown-paper") is None


def test_set_then_get_returns_same_object() -> None:
    bm25 = object()
    corpus = ["chunk-a", "chunk-b"]

    cache.set("paper-1", bm25, corpus)

    assert cache.get("paper-1") == (bm25, corpus)


def test_invalidate_drops_paper_scope_and_all_scope() -> None:
    cache.set("paper-1", object(), [])
    cache.set(None, object(), [])  # scope "__all__" (query không giới hạn paper)

    cache.invalidate("paper-1")

    assert cache.get("paper-1") is None
    assert cache.get(None) is None


def test_invalidate_does_not_touch_other_paper_scope() -> None:
    other_bm25, other_corpus = object(), ["x"]
    cache.set("paper-2", other_bm25, other_corpus)

    cache.invalidate("paper-1")

    assert cache.get("paper-2") == (other_bm25, other_corpus)


def test_ttl_expiry(monkeypatch) -> None:
    cache.set("paper-1", object(), [])

    future = time.monotonic() + cache._TTL_SECONDS + 1
    monkeypatch.setattr(time, "monotonic", lambda: future)

    assert cache.get("paper-1") is None
