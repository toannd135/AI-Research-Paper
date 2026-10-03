import time
from unittest.mock import MagicMock, patch

import pytest

from app.ai.llm_gateway.base import LLMGatewayError, Message


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


@patch("app.ai.llm_gateway.anthropic_adapter.get_settings")
def test_missing_api_key_raises_gateway_error(mock_get_settings):
    mock_get_settings.return_value = MagicMock(anthropic_api_key="")

    from app.ai.llm_gateway.anthropic_adapter import AnthropicAdapter

    with pytest.raises(LLMGatewayError):
        AnthropicAdapter(api_key="")


@patch("app.ai.llm_gateway.anthropic_adapter.anthropic.Anthropic")
def test_generate_returns_text_from_text_blocks(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    text_block = MagicMock(type="text", text="Đây là câu trả lời từ Claude.")
    mock_client.messages.create.return_value = MagicMock(content=[text_block])

    from app.ai.llm_gateway.anthropic_adapter import AnthropicAdapter

    adapter = AnthropicAdapter(api_key="fake-key")
    result = adapter.generate(
        [Message(role="system", content="Bạn là trợ lý."), Message(role="user", content="Xin chào")],
        model_name="claude-sonnet-5",
    )

    assert result.text == "Đây là câu trả lời từ Claude."
    assert result.model == "claude-sonnet-5"
    _, kwargs = mock_client.messages.create.call_args
    assert kwargs["system"] == "Bạn là trợ lý."
    assert kwargs["messages"] == [{"role": "user", "content": "Xin chào"}]


@patch("app.ai.llm_gateway.anthropic_adapter.anthropic.Anthropic")
def test_empty_response_raises_gateway_error(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = MagicMock(content=[])

    from app.ai.llm_gateway.anthropic_adapter import AnthropicAdapter

    adapter = AnthropicAdapter(api_key="fake-key")
    with pytest.raises(LLMGatewayError):
        adapter.generate([Message(role="user", content="Hi")])


@patch("app.ai.llm_gateway.anthropic_adapter.anthropic.Anthropic")
def test_sdk_exception_wrapped_as_gateway_error(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = RuntimeError("network timeout")

    from app.ai.llm_gateway.anthropic_adapter import AnthropicAdapter

    adapter = AnthropicAdapter(api_key="fake-key")
    with pytest.raises(LLMGatewayError):
        adapter.generate([Message(role="user", content="Hi")])


@patch("app.ai.llm_gateway.anthropic_adapter.anthropic.Anthropic")
def test_retries_transient_error_then_succeeds(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    text_block = MagicMock(type="text", text="Trả lời sau khi retry.")
    mock_client.messages.create.side_effect = [RuntimeError("timeout"), MagicMock(content=[text_block])]

    from app.ai.llm_gateway.anthropic_adapter import AnthropicAdapter

    adapter = AnthropicAdapter(api_key="fake-key")
    result = adapter.generate([Message(role="user", content="Hi")])

    assert result.text == "Trả lời sau khi retry."
    assert mock_client.messages.create.call_count == 2
