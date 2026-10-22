"""Test POST /research, GET /research/{id} — mock clarify() và Celery .delay(), DB SQLite in-memory."""

from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.llm_gateway.base import LLMGatewayError
from app.core.database import Base, get_db
from app.api.models.research_task import ResearchTask
from app.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("params,columns", [({}, 2), ({"columns": "2"}, 2), ({"columns": "1"}, 1)])
def test_pdf_export_parses_column_query(client, params, columns):
    db = MagicMock()
    db.get.return_value = SimpleNamespace(report="# Paper\n\n## 1. Method\nEvidence.", citations=None, user_id=None)
    app.dependency_overrides[get_db] = lambda: db
    with patch("app.pipeline.export.pdf_renderer.report_to_pdf", return_value=b"%PDF-test") as render:
        response = client.get("/research/test-task/pdf", params=params)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    render.assert_called_once_with(ANY, columns=columns)


@pytest.mark.parametrize("columns", ["0", "3", "invalid"])
def test_pdf_export_rejects_invalid_column_count(client, columns):
    assert client.get("/research/test-task/pdf", params={"columns": columns}).status_code == 422


@patch("app.api.routes.research.run_research")
@patch("app.api.routes.research.clarify")
def test_create_research_returns_clarification_questions_without_creating_task(
    mock_clarify, mock_run_research, client
):
    mock_clarify.return_value = {
        "status": "needs_clarification",
        "questions": [{"text": "Phạm vi là gì?", "suggestions": ["Rộng", "Hẹp"]}],
    }

    response = client.post("/research/", json={"question": "So sánh các phương pháp"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_clarification"
    assert body["questions"] == [{"text": "Phạm vi là gì?", "suggestions": ["Rộng", "Hẹp"]}]
    mock_run_research.delay.assert_not_called()


@patch("app.api.routes.research.run_research")
@patch("app.api.routes.research.clarify")
def test_create_research_creates_task_and_triggers_celery_when_ready(
    mock_clarify, mock_run_research, client
):
    mock_clarify.return_value = {"status": "ready", "refined_question": "So sánh BM25 và vector search"}

    response = client.post("/research/", json={"question": "So sánh BM25 và vector search"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["id"]
    mock_run_research.delay.assert_called_once_with(body["id"])


@patch("app.api.routes.research.run_research")
@patch("app.api.routes.research.clarify")
def test_create_research_returns_503_instead_of_500_when_llm_gateway_fails(
    mock_clarify, mock_run_research, client
):
    """Trước đây LLMGatewayError (vd: Gemini quota exceeded) không được catch, làm /research/ trả 500 trần trụi."""
    mock_clarify.side_effect = LLMGatewayError("Gemini API lỗi: 429 quota exceeded")

    response = client.post("/research/", json={"question": "So sánh các phương pháp"})

    assert response.status_code == 503
    assert "quota" in response.json()["detail"].lower()
    mock_run_research.delay.assert_not_called()


@patch("app.api.routes.research.run_research")
@patch("app.api.routes.research.clarify")
def test_get_research_returns_404_when_not_found(mock_clarify, mock_run_research, client):
    response = client.get("/research/does-not-exist")

    assert response.status_code == 404


@patch("app.api.routes.research.run_research")
@patch("app.api.routes.research.clarify")
def test_get_research_returns_task_status(mock_clarify, mock_run_research, client):
    mock_clarify.return_value = {"status": "ready", "refined_question": "câu hỏi"}

    created = client.post("/research/", json={"question": "câu hỏi"}).json()

    response = client.get(f"/research/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["status"] == "pending"
    assert body["citations"] == []


def test_research_history_paginates_filters_and_preserves_reports(client):
    from datetime import datetime, timedelta, timezone

    session = app.dependency_overrides[get_db]()
    db = next(session)
    try:
        for index, status in enumerate(("done", "pending", "done")):
            db.add(ResearchTask(
                id=f"history-{index}", question=f"Question {index}", refined_question=f"Refined {index}",
                status=status, report="# Saved report" if status == "done" else None,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            ))
        db.commit()
    finally:
        session.close()

    for path in ("/research", "/research/"):
        response = client.get(path, params={"limit": 1, "offset": 1})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert body["items"][0]["id"] == "history-1"
        assert body["items"][0]["has_report"] is False
        assert "report" not in body["items"][0]

    body = client.get("/research", params={"status": "done"}).json()
    assert body["total"] == 2
    assert [task["id"] for task in body["items"]] == ["history-2", "history-0"]
    assert all(task["has_report"] for task in body["items"])
    restored = client.get("/research/history-2").json()
    assert restored["question"] == "Question 2"
    assert restored["refined_question"] == "Refined 2"
    assert restored["report"] == "# Saved report"


def test_delete_research_removes_task_even_when_processing(client):
    session = next(app.dependency_overrides[get_db]())
    session.add(ResearchTask(id="running-1", question="Q", status="processing"))
    session.commit()

    assert client.delete("/research/running-1").status_code == 204
    assert client.get("/research/running-1").status_code == 404
    assert client.delete("/research/running-1").status_code == 404
