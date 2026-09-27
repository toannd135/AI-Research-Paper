import time
from unittest.mock import MagicMock, patch

import pytest

from app.ai.llm_gateway.base import LLMGatewayError, Message


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


@patch("app.ai.llm_gateway.openai_adapter.get_settings")
def test_missing_api_key_raises_gateway_error(mock_get_settings):
    mock_get_settings.return_value = MagicMock(openai_api_key="")

    from app.ai.llm_gateway.openai_adapter import OpenAIAdapter

    with pytest.raises(LLMGatewayError):
        OpenAIAdapter(api_key="")


def _completion(text: str) -> MagicMock:
    message = MagicMock(content=text)
    choice = MagicMock(message=message)
    return MagicMock(choices=[choice])


@patch("app.ai.llm_gateway.openai_adapter.openai.OpenAI")
def test_generate_returns_text(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _completion("Đây là câu trả lời từ GPT.")

    from app.ai.llm_gateway.openai_adapter import OpenAIAdapter

    adapter = OpenAIAdapter(api_key="fake-key")
    result = adapter.generate(
        [Message(role="system", content="Bạn là trợ lý."), Message(role="user", content="Xin chào")],
        model_name="gpt-5.6",
    )

    assert result.text == "Đây là câu trả lời từ GPT."
    assert result.model == "gpt-5.6"
    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["messages"] == [
        {"role": "system", "content": "Bạn là trợ lý."},
        {"role": "user", "content": "Xin chào"},
    ]


@patch("app.ai.llm_gateway.openai_adapter.openai.OpenAI")
def test_empty_response_raises_gateway_error(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _completion("")

    from app.ai.llm_gateway.openai_adapter import OpenAIAdapter

    adapter = OpenAIAdapter(api_key="fake-key")
    with pytest.raises(LLMGatewayError):
        adapter.generate([Message(role="user", content="Hi")])


@patch("app.ai.llm_gateway.openai_adapter.openai.OpenAI")
def test_sdk_exception_wrapped_as_gateway_error(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = RuntimeError("network timeout")

    from app.ai.llm_gateway.openai_adapter import OpenAIAdapter

    adapter = OpenAIAdapter(api_key="fake-key")
    with pytest.raises(LLMGatewayError):
        adapter.generate([Message(role="user", content="Hi")])


@patch("app.ai.llm_gateway.openai_adapter.openai.OpenAI")
def test_retries_transient_error_then_succeeds(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [RuntimeError("timeout"), _completion("Trả lời sau khi retry.")]

    from app.ai.llm_gateway.openai_adapter import OpenAIAdapter

    adapter = OpenAIAdapter(api_key="fake-key")
    result = adapter.generate([Message(role="user", content="Hi")])

    assert result.text == "Trả lời sau khi retry."
    assert mock_client.chat.completions.create.call_count == 2
