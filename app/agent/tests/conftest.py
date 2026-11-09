import pytest


@pytest.fixture(autouse=True)
def _no_real_qdrant_for_corpus_coverage(monkeypatch):
    """Test không chạm Qdrant thật: bước bổ sung độ phủ kho coi như kho rỗng (test riêng ghi đè lại)."""
    monkeypatch.setattr("app.agent.tools.ensure_coverage.list_paper_ids", lambda: set())


@pytest.fixture(autouse=True)
def _extract_cache_in_tmp(monkeypatch, tmp_path):
    """Tắt cache trích xuất mặc định (test dùng cùng evidence với phản hồi giả khác nhau); test cache tự bật lại."""
    monkeypatch.setattr("app.agent.evidence.extractor.CACHE_ENABLED", False)
    monkeypatch.setattr("app.agent.evidence.extractor._cache_dir", lambda: tmp_path / "extract_cache")
