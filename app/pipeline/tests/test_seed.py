from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.models.paper import Paper
from app.core.database import Base
from app.pipeline import seed


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_import_is_idempotent_and_skips_duplicate_content(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1 same")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1 same")
    (tmp_path / "c.pdf").write_bytes(b"%PDF-1 other")
    db = _db()
    with patch.object(seed.process_paper, "delay") as delay:
        assert seed.import_existing_papers(db) == 2
        assert seed.import_existing_papers(db) == 0
    assert delay.call_count == 2
    assert db.query(Paper).count() == 2
    get_settings.cache_clear()
