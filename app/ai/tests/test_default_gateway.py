"""Test chọn provider mặc định cho agent: AGENT_PROVIDER ép buộc, thứ tự ưu tiên theo key, lỗi rõ ràng khi thiếu key."""

from unittest.mock import MagicMock, patch

import pytest

from app.ai.llm_gateway import default as default_mod
from app.ai.llm_gateway.base import LLMGatewayError


def _settings(**overrides) -> MagicMock:
    base = {
        "agent_provider": None,
        "openrouter_api_key": None,
        "groq_api_key": None,
        "gemini_api_key": "",
        "anthropic_api_key": None,
        "openai_api_key": None,
        "openrouter_model": "or-model",
        "groq_model": "groq-model",
    }
    base.update(overrides)
    return MagicMock(**base)


def test_returns_injected_llm_first():
    fake = MagicMock()
    assert default_mod.get_default_agent_gateway(fake) == (fake, "default")


@patch("app.ai.llm_gateway.default.GeminiAdapter")
@patch("app.ai.llm_gateway.default.get_settings")
def test_picks_first_provider_with_key(mock_get_settings, mock_gemini):
    mock_get_settings.return_value = _settings(gemini_api_key="g-key")

    gateway, model = default_mod.get_default_agent_gateway()

    assert gateway is mock_gemini.return_value
    assert model == default_mod.GEMINI_DEFAULT_MODEL


@patch("app.ai.llm_gateway.default.GroqAdapter")
@patch("app.ai.llm_gateway.default.get_settings")
def test_agent_provider_setting_forces_provider(mock_get_settings, mock_groq):
    mock_get_settings.return_value = _settings(agent_provider="groq", gemini_api_key="g-key", groq_api_key="k")

    gateway, model = default_mod.get_default_agent_gateway()

    assert gateway is mock_groq.return_value
    assert model == "groq-model"


@patch("app.ai.llm_gateway.default.get_settings")
def test_raises_clear_error_when_no_key_configured(mock_get_settings):
    mock_get_settings.return_value = _settings()

    with pytest.raises(LLMGatewayError, match="API key"):
        default_mod.get_default_agent_gateway()
