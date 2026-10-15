"""Chọn LLM Gateway mặc định cho toàn bộ hệ thống Agent (clarify/plan/analyze/critique/synthesize)."""

import logging

from app.ai.llm_gateway.anthropic_adapter import DEFAULT_MODEL as ANTHROPIC_DEFAULT_MODEL
from app.ai.llm_gateway.anthropic_adapter import AnthropicAdapter
from app.ai.llm_gateway.base import LLMGateway, LLMGatewayError
from app.ai.llm_gateway.gemini_adapter import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL
from app.ai.llm_gateway.gemini_adapter import GeminiAdapter
from app.ai.llm_gateway.groq_adapter import DEFAULT_MODEL as GROQ_DEFAULT_MODEL
from app.ai.llm_gateway.groq_adapter import GroqAdapter
from app.ai.llm_gateway.openai_adapter import DEFAULT_MODEL as OPENAI_DEFAULT_MODEL
from app.ai.llm_gateway.openai_adapter import OpenAIAdapter
from app.ai.llm_gateway.openrouter_adapter import DEFAULT_MODEL as OPENROUTER_DEFAULT_MODEL
from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Thứ tự ưu tiên khi AGENT_PROVIDER không được đặt: provider đầu tiên có API key sẽ được dùng.
_PROVIDER_ORDER = ("openrouter", "groq", "gemini", "anthropic", "openai")


def _build(provider: str, settings: Settings) -> tuple[LLMGateway, str]:
    if provider == "openrouter":
        return OpenRouterAdapter(), settings.openrouter_model or OPENROUTER_DEFAULT_MODEL
    if provider == "groq":
        return GroqAdapter(), settings.groq_model or GROQ_DEFAULT_MODEL
    if provider == "gemini":
        return GeminiAdapter(), GEMINI_DEFAULT_MODEL
    if provider == "anthropic":
        return AnthropicAdapter(), ANTHROPIC_DEFAULT_MODEL
    if provider == "openai":
        return OpenAIAdapter(), OPENAI_DEFAULT_MODEL
    raise LLMGatewayError(f"AGENT_PROVIDER không hợp lệ: {provider!r}")


def _has_key(provider: str, settings: Settings) -> bool:
    return bool(
        {
            "openrouter": settings.openrouter_api_key,
            "groq": settings.groq_api_key,
            "gemini": settings.gemini_api_key,
            "anthropic": settings.anthropic_api_key,
            "openai": settings.openai_api_key,
        }[provider]
    )


def get_default_agent_gateway(llm: LLMGateway | None = None) -> tuple[LLMGateway, str]:
    """Trả về (gateway, model_name).

    Ưu tiên:
    1. `llm` được truyền trực tiếp (test/mock hoặc caller tự chọn).
    2. Provider ép bởi AGENT_PROVIDER trong .env.
    3. Provider đầu tiên trong _PROVIDER_ORDER có API key.
    Không có key nào -> LLMGatewayError rõ ràng thay vì lỗi ngầm ở adapter.
    """
    if llm is not None:
        return llm, "default"

    settings = get_settings()
    if settings.agent_provider:
        return _build(settings.agent_provider, settings)

    for provider in _PROVIDER_ORDER:
        if _has_key(provider, settings):
            return _build(provider, settings)

    raise LLMGatewayError(
        "Chưa cấu hình API key cho LLM nào (OPENROUTER_API_KEY / GROQ_API_KEY / GEMINI_API_KEY / "
        "ANTHROPIC_API_KEY / OPENAI_API_KEY). Xem .env.example."
    )
