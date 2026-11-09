"""Workspace: paper upload vào phiên A không được truy xuất ở phiên B / lượt không chỉ định phiên (cùng một user)."""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.models.paper import Paper
from app.api.models.workspace import Workspace
from app.core.database import Base
from app.core.scope import allowed_paper_ids_for

ALICE = SimpleNamespace(id="alice", role="user")
BOB = SimpleNamespace(id="bob", role="user")
ADMIN = SimpleNamespace(id="adm", role="admin")


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all(
        [
            Workspace(id="wA", user_id="alice", name="deepfake"),
            Workspace(id="wB", user_id="alice", name="brain"),
            Paper(id="p1", filename="a", file_path="/x/a.pdf", status="done", user_id="alice", workspace_id="wA"),
            Paper(id="p2", filename="b", file_path="/x/b.pdf", status="done", user_id="alice", workspace_id="wB"),
            Paper(id="p3", filename="c", file_path="/x/c.pdf", status="done", user_id="alice", workspace_id=None),
            Paper(id="p4", filename="d", file_path="/x/d.pdf", status="done", user_id="bob", workspace_id=None),
        ]
    )
    session.commit()
    yield session
    session.close()


def test_workspace_only_sees_its_own_papers(db):
    assert allowed_paper_ids_for(db, ALICE, "wA") == {"p1"}
    assert allowed_paper_ids_for(db, ALICE, "wB") == {"p2"}


def test_no_workspace_excludes_assigned_papers(db):
    assert allowed_paper_ids_for(db, ALICE) == {"p3"}  # p1/p2 thuộc phiên, không rò sang lượt không chỉ định
    assert allowed_paper_ids_for(db, BOB) == {"p4"}


def test_admin_without_workspace_unrestricted_but_workspace_applies(db):
    assert allowed_paper_ids_for(db, ADMIN) is None
    assert allowed_paper_ids_for(db, ADMIN, "wA") == {"p1"}
