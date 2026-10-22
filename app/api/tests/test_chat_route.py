"""Test POST /chat, GET /chat/models — mock retrieval + LLM gateway, DB SQLite in-memory."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.llm_gateway.base import LLMGatewayError, LLMResponse
from app.ai.llm_gateway.registry import AVAILABLE_MODELS, DEFAULT_MODEL_ID
from app.core.config import Settings
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
    test_client = TestClient(app)
    test_client.session_factory = TestingSessionLocal
    yield test_client
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
    assert body["model"] == DEFAULT_MODEL_ID


@patch("app.api.routes.chat.build_gateway")
@patch("app.api.routes.chat.rerank")
@patch("app.api.routes.chat.search_hybrid")
@pytest.mark.parametrize("model_id,model_name", [
    ("claude-sonnet-5", None),
    ("openrouter:vendor/primary", "vendor/primary"),
    ("openrouter:vendor/fallback", "vendor/fallback"),
])
def test_chat_uses_requested_model(mock_hybrid, mock_rerank, mock_build_gateway, client, model_id, model_name):
    mock_hybrid.return_value = _candidates()
    mock_rerank.return_value = _candidates()
    mock_build_gateway.return_value = _fake_gateway(text="Trả lời từ Claude.")

    with patch("app.ai.llm_gateway.registry.get_settings", return_value=Settings(
        _env_file=None,
        openrouter_model="vendor/primary",
        openrouter_fallback_models=["vendor/fallback"],
    )):
        response = client.post(
            "/chat", json={"question": "Phương pháp là gì?", "model": model_id}
        )

    assert response.status_code == 200
    assert response.json()["model"] == model_id
    assert mock_build_gateway.call_args.args[0].id == model_id
    if model_name:
        assert mock_build_gateway.return_value.generate.call_args.kwargs["model_name"] == model_name


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


@patch("app.ai.llm_gateway.registry.get_settings")
def test_list_chat_models_reports_availability(mock_get_settings, client):
    mock_get_settings.return_value = Settings(
        _env_file=None,
        openrouter_api_key="test-key",
        openrouter_model="vendor/primary",
        openrouter_fallback_models=["vendor/fallback"],
    )
    response = client.get("/chat/models")

    assert response.status_code == 200
    models = {m["id"]: m for m in response.json()}
    assert set(models) == {option.id for option in AVAILABLE_MODELS} | {
        "openrouter:vendor/primary", "openrouter:vendor/fallback",
    }
    assert models["openrouter:vendor/primary"]["available"] is True
    assert models["openrouter:vendor/fallback"]["available"] is True

    mock_get_settings.return_value.openrouter_api_key = ""
    models = {m["id"]: m for m in client.get("/chat/models").json()}
    assert models["openrouter:vendor/primary"]["available"] is False


@patch("app.api.routes.chat.build_gateway")
@patch("app.api.routes.chat.rerank")
@patch("app.api.routes.chat.search_hybrid")
def test_conversation_is_restorable_by_research_task(mock_hybrid, mock_rerank, mock_build_gateway, client):
    mock_hybrid.return_value = _candidates()
    mock_rerank.return_value = _candidates()
    mock_build_gateway.return_value = _fake_gateway(text="Câu trả lời.")

    from app.api.models.research_task import ResearchTask

    with client.session_factory() as db:
        db.add(ResearchTask(id="task-1", question="q", status="done"))
        db.commit()

    assert client.get("/conversations/by-research/task-1").json()["messages"] == []

    client.post("/chat", json={"question": "Hỏi thêm?", "research_task_id": "task-1"})

    body = client.get("/conversations/by-research/task-1").json()
    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", "Hỏi thêm?"),
        ("assistant", "Câu trả lời."),
    ]
    assert body["messages"][1]["citations"], "trích dẫn phải được lưu cùng câu trả lời"
