"""Cung cấp default LLM Gateway cho toàn bộ hệ thống Agent."""

from app.ai.llm_gateway.base import LLMGateway
from app.ai.llm_gateway.gemini_adapter import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL
from app.ai.llm_gateway.gemini_adapter import GeminiAdapter
from app.ai.llm_gateway.groq_adapter import DEFAULT_MODEL as GROQ_DEFAULT_MODEL
from app.ai.llm_gateway.groq_adapter import GroqAdapter
from app.ai.llm_gateway.openrouter_adapter import DEFAULT_MODEL as OPENROUTER_DEFAULT_MODEL
from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter
from app.core.config import get_settings


def get_default_agent_gateway(llm: LLMGateway | None = None) -> tuple[LLMGateway, str]:
    """Trả về (gateway, model_name).

    Ưu tiên:
    1. `llm` được truyền trực tiếp (thường dùng trong test mock).
    2. `OpenRouterAdapter` nếu có OPENROUTER_API_KEY.
    3. `GroqAdapter` nếu có GROQ_API_KEY.
    4. `GeminiAdapter` nếu có GEMINI_API_KEY.
    5. Mặc định `OpenRouterAdapter` (hoặc GroqAdapter).
    """
    if llm is not None:
        return llm, "default"

    settings = get_settings()
    if settings.openrouter_api_key:
        return OpenRouterAdapter(), settings.openrouter_model or OPENROUTER_DEFAULT_MODEL

    if settings.groq_api_key:
        return GroqAdapter(), settings.groq_model or GROQ_DEFAULT_MODEL

    if settings.gemini_api_key:
        return GeminiAdapter(), GEMINI_DEFAULT_MODEL

    # Mặc định sử dụng OpenRouterAdapter nếu có key, ngược lại GroqAdapter
    if settings.openrouter_api_key:
        return OpenRouterAdapter(), settings.openrouter_model or OPENROUTER_DEFAULT_MODEL
    return GroqAdapter(), settings.groq_model or GROQ_DEFAULT_MODEL
