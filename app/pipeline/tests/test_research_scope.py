"""Phạm vi research chỉ gồm paper done trong DB (loại vector mồ côi trong Qdrant)."""

from types import SimpleNamespace

import pytest

from app.pipeline.tasks import _require_indexed_papers, _research_scope


def _db(done_ids):
    return SimpleNamespace(scalars=lambda _stmt: SimpleNamespace(all=lambda: list(done_ids)))


def test_admin_scope_is_done_papers_not_unlimited():
    assert _research_scope(_db({"a", "b"}), None) == {"a", "b"}


def test_user_scope_intersects_done_papers():
    assert _research_scope(_db({"a", "b"}), {"b", "c"}) == {"b"}


def test_no_done_paper_keeps_previous_scope():
    assert _research_scope(_db(set()), None) is None
    assert _research_scope(_db(set()), {"x"}) == {"x"}


def test_workspace_without_indexed_paper_is_rejected():
    with pytest.raises(ValueError, match="chưa có PDF"):
        _require_indexed_papers(SimpleNamespace(scalar=lambda _stmt: 0), "ws")


def test_workspace_with_indexed_paper_passes():
    _require_indexed_papers(SimpleNamespace(scalar=lambda _stmt: 2), "ws")
