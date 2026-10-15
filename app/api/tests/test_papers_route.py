"""Test /papers: upload validate PDF + size, list/paginate, reprocess, delete — mock Celery + Qdrant, SQLite in-memory."""

import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "papers"))
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _upload(client, name="a.pdf", content=b"%PDF-1.4 hello"):
    return client.post("/papers/upload", files={"file": (name, io.BytesIO(content), "application/pdf")})


@patch("app.api.routes.papers.process_paper")
def test_upload_rejects_non_pdf_extension(mock_task, client):
    response = _upload(client, name="a.txt")
    assert response.status_code == 400
    mock_task.delay.assert_not_called()


@patch("app.api.routes.papers.process_paper")
def test_upload_rejects_file_without_pdf_header(mock_task, client):
    response = _upload(client, content=b"not a pdf at all")
    assert response.status_code == 400
    assert "%PDF" in response.json()["detail"]
    mock_task.delay.assert_not_called()


@patch("app.api.routes.papers.process_paper")
def test_upload_rejects_oversized_file(mock_task, client):
    response = _upload(client, content=b"%PDF" + b"x" * (1024 * 1024 + 10))
    assert response.status_code == 413
    mock_task.delay.assert_not_called()


@patch("app.api.routes.papers.process_paper")
def test_upload_creates_pending_paper_and_queues_task(mock_task, client, tmp_path):
    response = _upload(client, name="../../evil/../paper.pdf")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["filename"] == "paper.pdf"  # chỉ giữ basename
    mock_task.delay.assert_called_once_with(body["id"])
    assert (tmp_path / "papers" / f"{body['id']}.pdf").exists()


@patch("app.api.routes.papers.process_paper")
def test_list_papers_paginates_and_filters(mock_task, client):
    ids = [_upload(client, name=f"p{i}.pdf").json()["id"] for i in range(3)]

    response = client.get("/papers", params={"limit": 2, "offset": 0})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert {item["id"] for item in body["items"]} <= set(ids)

    filtered = client.get("/papers", params={"status": "done"}).json()
    assert filtered["total"] == 0


@patch("app.api.routes.papers.process_paper")
def test_reprocess_requeues_paper(mock_task, client):
    paper_id = _upload(client).json()["id"]
    mock_task.delay.reset_mock()

    response = client.post(f"/papers/{paper_id}/reprocess")

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    mock_task.delay.assert_called_once_with(paper_id)


@patch("app.pipeline.vector_store.qdrant_client.delete_paper")
@patch("app.api.routes.papers.process_paper")
def test_delete_paper_removes_file_vectors_and_record(mock_task, mock_delete_vectors, client, tmp_path):
    paper_id = _upload(client).json()["id"]

    response = client.delete(f"/papers/{paper_id}")

    assert response.status_code == 204
    mock_delete_vectors.assert_called_once_with(paper_id)
    assert not (tmp_path / "papers" / f"{paper_id}.pdf").exists()
    assert client.get(f"/papers/{paper_id}").status_code == 404


def test_get_unknown_paper_returns_404(client):
    assert client.get("/papers/nope").status_code == 404
