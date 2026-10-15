import time
from unittest.mock import MagicMock, patch

import pytest

from app.ai.llm_gateway.base import LLMGatewayError, Message


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


@patch("app.ai.llm_gateway.openrouter_adapter.get_settings")
def test_missing_openrouter_api_key_raises_gateway_error(mock_get_settings):
    mock_get_settings.return_value = MagicMock(openrouter_api_key="")

    from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter

    with pytest.raises(LLMGatewayError):
        OpenRouterAdapter(api_key="")


@patch("app.ai.llm_gateway.openrouter_adapter.httpx.Client")
def test_openrouter_generate_returns_text(mock_httpx_cls):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "choices": [{"message": {"content": "Báo cáo nghiên cứu từ OpenRouter."}}],
    }
    mock_client = MagicMock()
    mock_client.post.return_value = mock_res
    mock_httpx_cls.return_value.__enter__.return_value = mock_client

    from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter

    adapter = OpenRouterAdapter(api_key="sk-or-fake-key")
    result = adapter.generate([Message(role="user", content="Xin chào")])

    assert result.text == "Báo cáo nghiên cứu từ OpenRouter."
    assert result.model == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert mock_client.post.call_count == 1


@patch("app.ai.llm_gateway.openrouter_adapter.httpx.Client")
def test_openrouter_upstream_error_raises_gateway_error(mock_httpx_cls):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "error": {"message": "Service temporarily overloaded", "code": 503}
    }
    mock_client = MagicMock()
    mock_client.post.return_value = mock_res
    mock_httpx_cls.return_value.__enter__.return_value = mock_client

    from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter

    adapter = OpenRouterAdapter(api_key="sk-or-fake-key")
    with pytest.raises(LLMGatewayError) as exc_info:
        adapter.generate([Message(role="user", content="Hi")])
    assert "OpenRouter upstream error" in str(exc_info.value)
