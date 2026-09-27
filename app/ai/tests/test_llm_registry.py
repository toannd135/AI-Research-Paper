from unittest.mock import MagicMock, patch

from app.ai.llm_gateway.registry import AVAILABLE_MODELS, DEFAULT_MODEL_ID, is_configured, resolve_model


def test_resolve_model_returns_default_when_id_is_none():
    option = resolve_model(None)
    assert option.id == DEFAULT_MODEL_ID


def test_resolve_model_returns_default_when_id_unknown():
    option = resolve_model("not-a-real-model")
    assert option.id == DEFAULT_MODEL_ID


def test_resolve_model_returns_requested_option():
    option = resolve_model("claude-sonnet-5")
    assert option.id == "claude-sonnet-5"


@patch("app.ai.llm_gateway.registry.get_settings")
def test_is_configured_reflects_required_setting(mock_get_settings):
    mock_get_settings.return_value = MagicMock(gemini_api_key="key", anthropic_api_key=None, openai_api_key="")

    by_id = {option.id: option for option in AVAILABLE_MODELS}
    assert is_configured(by_id["gemini-3.6-flash"]) is True
    assert is_configured(by_id["claude-sonnet-5"]) is False
    assert is_configured(by_id["gpt-5.6"]) is False
