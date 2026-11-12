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


@pytest.fixture(autouse=True)
def _reset_domain():
    """Mỗi test bắt đầu ở chế độ chung; không để chế độ của test trước rò sang."""
    from app.agent.domains import set_domain

    set_domain(None)
    yield
    set_domain(None)


@pytest.fixture
def mri_domain():
    """Test dùng fixture BraTS/MRI: bật chế độ MRI não."""
    from app.agent.domains import MRI_BRAIN, set_domain

    set_domain(MRI_BRAIN)
    yield


@pytest.fixture
def deepfake_domain():
    from app.agent.domains import DEEPFAKE, set_domain

    set_domain(DEEPFAKE)
    yield
