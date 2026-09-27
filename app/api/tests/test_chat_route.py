"""Test POST /chat, GET /chat/models — mock retrieval + LLM gateway, DB SQLite in-memory."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.llm_gateway.base import LLMGatewayError, LLMResponse
from app.core.database import Base, get_db
from app.core.schemas import Chunk, ScoredChunk
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


def _candidates() -> list[ScoredChunk]:
    return [ScoredChunk(chunk=Chunk(id="a", paper_id="p1", text="evidence text", chunk_index=0), score=0.9)]


def _fake_gateway(text: str | None = None, error: Exception | None = None) -> MagicMock:
    gateway = MagicMock()
    if error is not None:
        gateway.generate.side_effect = error
    else:
        gateway.generate.return_value = LLMResponse(text=text, model="fake")
    return gateway


@patch("app.api.routes.chat.build_gateway")
@patch("app.api.routes.chat.rerank")
@patch("app.api.routes.chat.search_hybrid")
def test_chat_returns_answer_on_success(mock_hybrid, mock_rerank, mock_build_gateway, client):
    mock_hybrid.return_value = _candidates()
    mock_rerank.return_value = _candidates()
    mock_build_gateway.return_value = _fake_gateway(text="Câu trả lời.")

    response = client.post("/chat", json={"question": "Phương pháp là gì?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Câu trả lời."
    assert body["model"] == "gemini-3.6-flash"  # model mặc định khi payload không chỉ định


@patch("app.api.routes.chat.build_gateway")
@patch("app.api.routes.chat.rerank")
@patch("app.api.routes.chat.search_hybrid")
def test_chat_uses_requested_model(mock_hybrid, mock_rerank, mock_build_gateway, client):
    mock_hybrid.return_value = _candidates()
    mock_rerank.return_value = _candidates()
    mock_build_gateway.return_value = _fake_gateway(text="Trả lời từ Claude.")

    response = client.post(
        "/chat", json={"question": "Phương pháp là gì?", "model": "claude-sonnet-5"}
    )

    assert response.status_code == 200
    assert response.json()["model"] == "claude-sonnet-5"


@patch("app.api.routes.chat.build_gateway")
@patch("app.api.routes.chat.rerank")
@patch("app.api.routes.chat.search_hybrid")
def test_chat_returns_404_when_no_relevant_chunks(mock_hybrid, mock_rerank, mock_build_gateway, client):
    mock_hybrid.return_value = []
    mock_rerank.return_value = []

    response = client.post("/chat", json={"question": "Phương pháp là gì?"})

    assert response.status_code == 404


@patch("app.api.routes.chat.build_gateway")
@patch("app.api.routes.chat.rerank")
@patch("app.api.routes.chat.search_hybrid")
def test_chat_returns_503_instead_of_500_when_llm_gateway_fails(
    mock_hybrid, mock_rerank, mock_build_gateway, client
):
    """Trước đây LLMGatewayError (vd: Gemini quota exceeded) không được catch, làm /chat trả 500 trần trụi."""
    mock_hybrid.return_value = _candidates()
    mock_rerank.return_value = _candidates()
    mock_build_gateway.return_value = _fake_gateway(error=LLMGatewayError("Gemini API lỗi: 429 quota exceeded"))

    response = client.post("/chat", json={"question": "Phương pháp là gì?"})

    assert response.status_code == 503
    assert "quota" in response.json()["detail"].lower()


def test_list_chat_models_reports_availability(client):
    response = client.get("/chat/models")

    assert response.status_code == 200
    models = {m["id"]: m for m in response.json()}
    assert set(models) == {"gemini-3.6-flash", "claude-sonnet-5", "gpt-5.6"}
    assert models["gemini-3.6-flash"]["available"] is True  # GEMINI_API_KEY luôn required, có trong .env test
