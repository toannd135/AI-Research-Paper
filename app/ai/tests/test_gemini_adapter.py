from unittest.mock import MagicMock, patch

import pytest

from app.ai.llm_gateway.base import LLMGatewayError, Message


@patch("app.ai.llm_gateway.gemini_adapter.get_settings")
def test_missing_api_key_raises_gateway_error(mock_get_settings):
    mock_get_settings.return_value = MagicMock(gemini_api_key="")

    from app.ai.llm_gateway.gemini_adapter import GeminiAdapter

    with pytest.raises(LLMGatewayError):
        GeminiAdapter(api_key="")


@patch("app.ai.llm_gateway.gemini_adapter.genai")
def test_generate_returns_text(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Đây là câu trả lời từ Gemini."
    mock_client.models.generate_content.return_value = mock_response

    from app.ai.llm_gateway.gemini_adapter import GeminiAdapter

    adapter = GeminiAdapter(api_key="fake-key")
    result = adapter.generate([Message(role="user", content="Xin chào")], model_name="gemini-2.5-flash")

    assert result.text == "Đây là câu trả lời từ Gemini."
    assert result.model == "gemini-2.5-flash"


@patch("app.ai.llm_gateway.gemini_adapter.genai")
def test_empty_response_raises_gateway_error(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = ""
    mock_client.models.generate_content.return_value = mock_response

    from app.ai.llm_gateway.gemini_adapter import GeminiAdapter

    adapter = GeminiAdapter(api_key="fake-key")
    with pytest.raises(LLMGatewayError):
        adapter.generate([Message(role="user", content="Hi")])


@patch("app.ai.llm_gateway.gemini_adapter.genai")
def test_sdk_exception_wrapped_as_gateway_error(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.generate_content.side_effect = RuntimeError("network timeout")

    from app.ai.llm_gateway.gemini_adapter import GeminiAdapter

    adapter = GeminiAdapter(api_key="fake-key")
    with pytest.raises(LLMGatewayError):
        adapter.generate([Message(role="user", content="Hi")])
