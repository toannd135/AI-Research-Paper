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


def test_assign_papers_to_user_scopes_retrieval(tmp_path):
    from app.api.models.user import User
    from app.core.scope import allowed_paper_ids_for

    folder = tmp_path / "df"
    other = tmp_path / "brain"
    folder.mkdir()
    other.mkdir()
    db = _db()
    alice = User(email="alice@x.com", password_hash="x")
    db.add_all(
        [
            alice,
            Paper(id="p1", filename="a.pdf", file_path=str(folder / "a.pdf"), status="done"),
            Paper(id="p2", filename="b.pdf", file_path=str(other / "b.pdf"), status="done"),
        ]
    )
    db.commit()

    dry = seed.assign_papers_to_user(db, folder, "Alice@x.com")
    assert [p.id for p in dry] == ["p1"]
    assert db.get(Paper, "p1").user_id is None  # dry-run không ghi

    seed.assign_papers_to_user(db, folder, "alice@x.com", apply=True)
    assert allowed_paper_ids_for(db, alice) == {"p1"}  # không thấy paper thư mục khác
    assert db.get(Paper, "p2").user_id is None

    import pytest

    with pytest.raises(ValueError):
        seed.assign_papers_to_user(db, folder, "ghost@x.com")


def test_assign_papers_with_workspace_creates_and_scopes(tmp_path):
    from app.api.models.user import User
    from app.api.models.workspace import Workspace
    from app.core.scope import allowed_paper_ids_for

    folder = tmp_path / "df"
    folder.mkdir()
    db = _db()
    alice = User(email="alice@x.com", password_hash="x")
    db.add_all([alice, Paper(id="p1", filename="a.pdf", file_path=str(folder / "a.pdf"), status="done")])
    db.commit()

    seed.assign_papers_to_user(db, folder, "alice@x.com", workspace_name="Deepfake")  # dry-run
    assert db.query(Workspace).count() == 0

    seed.assign_papers_to_user(db, folder, "alice@x.com", apply=True, workspace_name="Deepfake")
    ws = db.query(Workspace).one()
    assert db.get(Paper, "p1").workspace_id == ws.id
    assert allowed_paper_ids_for(db, alice, ws.id) == {"p1"}
    assert allowed_paper_ids_for(db, alice) == set()  # không rò sang lượt không chỉ định phiên
    # chạy lại không tạo workspace/đổi gì thêm
    assert seed.assign_papers_to_user(db, folder, "alice@x.com", apply=True, workspace_name="Deepfake") == []
    assert db.query(Workspace).count() == 1


def test_foreign_citation_ids_flags_sources_outside_dir(tmp_path):
    folder = tmp_path / "df"
    other = tmp_path / "brain"
    folder.mkdir()
    other.mkdir()
    db = _db()
    db.add_all(
        [
            Paper(id="in1", filename="a", file_path=str(folder / "a.pdf"), status="done"),
            Paper(id="out1", filename="b", file_path=str(other / "b.pdf"), status="done"),
            Paper(id="pend", filename="c", file_path=str(folder / "c.pdf"), status="pending"),
        ]
    )
    db.commit()
    cited = ["in1", "out1", "Some OpenAlex title", "in1", "pend"]
    assert seed.foreign_citation_ids(db, cited, folder) == ["out1", "Some OpenAlex title", "pend"]
