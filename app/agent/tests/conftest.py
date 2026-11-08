import pytest


@pytest.fixture(autouse=True)
def _no_real_qdrant_for_corpus_coverage(monkeypatch):
    """Test không chạm Qdrant thật: bước bổ sung độ phủ kho coi như kho rỗng (test riêng ghi đè lại)."""
    monkeypatch.setattr("app.agent.tools.ensure_coverage.list_paper_ids", lambda: set())
