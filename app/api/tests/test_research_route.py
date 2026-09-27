"""Test POST /research, GET /research/{id} — mock clarify() và Celery .delay(), DB SQLite in-memory."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.llm_gateway.base import LLMGatewayError
from app.core.database import Base, get_db
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
