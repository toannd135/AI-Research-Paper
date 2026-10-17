from unittest.mock import MagicMock, patch

from app.ai.llm_gateway.registry import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL_ID,
    is_configured,
    resolve_model,
)


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


def test_openrouter_is_selectable_in_chat():
    """Trước đây OpenRouter không có trong registry nên /chat không bao giờ gọi được, dù .env có key."""
    by_id = {option.id: option for option in AVAILABLE_MODELS}
    assert "openrouter" in by_id
    assert by_id["openrouter"].required_setting == "openrouter_api_key"


@patch("app.ai.llm_gateway.registry.get_settings")
def test_model_name_follows_env_setting(mock_get_settings):
    """OPENROUTER_MODEL / GROQ_MODEL trong .env phải được dùng thay cho hằng số mặc định."""
    from app.ai.llm_gateway.registry import resolve_model_name

    mock_get_settings.return_value = MagicMock(
        openrouter_model="meta-llama/llama-4-maverick:free", groq_model="llama-3.3-70b-versatile"
    )
    by_id = {option.id: option for option in AVAILABLE_MODELS}
    assert resolve_model_name(by_id["openrouter"]) == "meta-llama/llama-4-maverick:free"
    assert resolve_model_name(by_id["groq-gpt-oss-120b"]) == "llama-3.3-70b-versatile"


@patch("app.ai.llm_gateway.registry.get_settings")
def test_model_name_falls_back_to_default_when_env_empty(mock_get_settings):
    from app.ai.llm_gateway.openrouter_adapter import DEFAULT_MODEL as OPENROUTER_DEFAULT
    from app.ai.llm_gateway.registry import resolve_model_name

    mock_get_settings.return_value = MagicMock(openrouter_model="")
    by_id = {option.id: option for option in AVAILABLE_MODELS}
    assert resolve_model_name(by_id["openrouter"]) == OPENROUTER_DEFAULT


@patch("app.ai.llm_gateway.registry.get_settings")
def test_label_shows_actual_model_name(mock_get_settings):
    from app.ai.llm_gateway.registry import label_for

    mock_get_settings.return_value = MagicMock(openrouter_model="nvidia/nemotron:free", anthropic_model="claude-x", openai_model="gpt-x")
    by_id = {option.id: option for option in AVAILABLE_MODELS}
    assert label_for(by_id["openrouter"]) == "OpenRouter · nvidia/nemotron:free"
    assert label_for(by_id["claude-sonnet-5"]) == "Anthropic · claude-x"
    assert label_for(by_id["gpt-5.6"]) == "OpenAI · gpt-x"
    # Gemini chưa có biến model riêng nên nhãn giữ nguyên
    assert label_for(by_id["gemini-3.6-flash"]) == "Google · Gemini 3.6 Flash"


@patch("app.ai.llm_gateway.registry.get_settings")
def test_gemma_models_registered_with_own_key_and_model_name(mock_get_settings):
    from app.ai.llm_gateway.registry import is_configured, resolve_model_name

    by_id = {option.id: option for option in AVAILABLE_MODELS}
    mock_get_settings.return_value = MagicMock(
        gemma_31b_api_key="k31",
        gemma_26b_api_key=None,
        model_gemma_4_31b_it_free="google/gemma-4-31b-it:free",
        model_gemma_4_26b_a4b_free="google/gemma-4-26b-a4b:free",
    )
    assert is_configured(by_id["gemma-4-31b-it-free"])
    assert not is_configured(by_id["gemma-4-26b-a4b-free"])
    assert resolve_model_name(by_id["gemma-4-26b-a4b-free"]) == "google/gemma-4-26b-a4b:free"


def test_gemma_26b_key_accepts_legacy_misnamed_variable():
    from app.core.config import Settings

    s = Settings(_env_file=None, model_gemma_4_2b_it_free_key="legacy", openrouter_api_key="shared")
    assert s.gemma_26b_api_key == "legacy"
    assert Settings(_env_file=None, openrouter_api_key="shared").gemma_31b_api_key == "shared"
