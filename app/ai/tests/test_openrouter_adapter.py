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
def test_openrouter_models_array_capped_at_three(mock_httpx_cls):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"model": "m-main", "choices": [{"message": {"content": "ok"}}]}
    mock_client = MagicMock()
    mock_client.post.return_value = mock_res
    mock_httpx_cls.return_value.__enter__.return_value = mock_client

    from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter

    adapter = OpenRouterAdapter(api_key="sk-or-fake-key", fallback_models=["a", "b", "c"])
    adapter.generate([Message(role="user", content="Hi")], "m-main")

    sent = mock_client.post.call_args.kwargs["json"]["models"]
    assert sent == ["m-main", "a", "b"]


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


@patch("app.ai.llm_gateway.openrouter_adapter.httpx.Client")
def test_openrouter_429_raises_rate_limit_error_with_retry_after(mock_httpx_cls):
    from app.ai.llm_gateway.base import LLMRateLimitError
    from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter

    mock_res = MagicMock()
    mock_res.status_code = 429
    mock_res.text = "rate limited"
    mock_res.headers = {"retry-after": "12"}
    mock_client = MagicMock()
    mock_client.post.return_value = mock_res
    mock_httpx_cls.return_value.__enter__.return_value = mock_client

    adapter = OpenRouterAdapter(api_key="sk-or-fake-key")
    with pytest.raises(LLMRateLimitError) as exc_info:
        adapter.generate([Message(role="user", content="Hi")])
    assert exc_info.value.retry_after == 12.0


def _res(payload):
    res = MagicMock()
    res.status_code = 200
    res.json.return_value = payload
    return res


@patch("app.ai.llm_gateway.openrouter_adapter.httpx.Client")
def test_openrouter_empty_content_falls_back_to_next_model(mock_httpx_cls):
    mock_client = MagicMock()
    mock_client.post.side_effect = [
        _res({"model": "m-main", "choices": [{"message": {"content": None}, "finish_reason": "length"}]}),
        _res({"model": "a", "choices": [{"message": {"content": "ok"}}]}),
    ]
    mock_httpx_cls.return_value.__enter__.return_value = mock_client

    from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter

    adapter = OpenRouterAdapter(api_key="sk-or-fake-key", fallback_models=["a", "b", "c"])
    result = adapter.generate([Message(role="user", content="Hi")], "m-main")

    assert result.text == "ok"
    second = mock_client.post.call_args_list[1].kwargs["json"]["models"]
    assert second == ["a", "b", "c"]


@patch("app.ai.llm_gateway.openrouter_adapter.httpx.Client")
def test_openrouter_content_parts_list_is_joined(mock_httpx_cls):
    mock_client = MagicMock()
    mock_client.post.return_value = _res(
        {"model": "m", "choices": [{"message": {"content": [{"type": "text", "text": "xin "}, {"type": "text", "text": "chào"}]}}]}
    )
    mock_httpx_cls.return_value.__enter__.return_value = mock_client

    from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter

    result = OpenRouterAdapter(api_key="k").generate([Message(role="user", content="Hi")], "m")
    assert result.text == "xin chào"
