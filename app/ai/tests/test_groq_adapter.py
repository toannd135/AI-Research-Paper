import time
from unittest.mock import MagicMock, patch

import pytest

from app.ai.llm_gateway.base import LLMGatewayError, Message


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


@patch("app.ai.llm_gateway.groq_adapter.get_settings")
def test_missing_groq_api_key_raises_gateway_error(mock_get_settings):
    mock_get_settings.return_value = MagicMock(groq_api_key="")

    from app.ai.llm_gateway.groq_adapter import GroqAdapter

    with pytest.raises(LLMGatewayError):
        GroqAdapter(api_key="")


def _completion(text: str) -> MagicMock:
    message = MagicMock(content=text)
    choice = MagicMock(message=message)
    return MagicMock(choices=[choice])


@patch("app.ai.llm_gateway.groq_adapter.openai.OpenAI")
def test_generate_returns_text_via_sdk(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _completion("Báo cáo IMRaD từ Llama 3.3.")

    from app.ai.llm_gateway.groq_adapter import GroqAdapter

    adapter = GroqAdapter(api_key="gsk_fake_key")
    result = adapter.generate(
        [Message(role="system", content="Hệ thống"), Message(role="user", content="Viết bài")],
        model_name="llama-3.3-70b-versatile",
    )

    assert result.text == "Báo cáo IMRaD từ Llama 3.3."
    assert result.model == "llama-3.3-70b-versatile"
    assert mock_client.chat.completions.create.call_count == 1


@patch("app.ai.llm_gateway.groq_adapter.httpx.Client")
def test_generate_returns_text_via_httpx_when_sdk_fails(mock_httpx_cls):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "choices": [{"message": {"content": "Kết quả từ HTTPX fallback"}}]
    }
    mock_client_instance = MagicMock()
    mock_client_instance.post.return_value = mock_res
    mock_httpx_cls.return_value.__enter__.return_value = mock_client_instance

    from app.ai.llm_gateway.groq_adapter import GroqAdapter

    adapter = GroqAdapter(api_key="gsk_fake_key")
    adapter._client = None  # simulate no OpenAI SDK

    result = adapter.generate([Message(role="user", content="Hi")])
    assert result.text == "Kết quả từ HTTPX fallback"
    assert mock_client_instance.post.call_count == 1
