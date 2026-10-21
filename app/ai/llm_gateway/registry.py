"""Danh sách model user có thể chọn ở chat UI — map model id (client gửi lên) -> adapter thật."""

from dataclasses import dataclass

from app.ai.llm_gateway.anthropic_adapter import (
    DEFAULT_MODEL as ANTHROPIC_DEFAULT_MODEL,
)
from app.ai.llm_gateway.anthropic_adapter import AnthropicAdapter
from app.ai.llm_gateway.base import LLMGateway
from app.ai.llm_gateway.gemini_adapter import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL
from app.ai.llm_gateway.gemini_adapter import GeminiAdapter
from app.ai.llm_gateway.groq_adapter import DEFAULT_MODEL as GROQ_DEFAULT_MODEL
from app.ai.llm_gateway.groq_adapter import GroqAdapter
from app.ai.llm_gateway.openai_adapter import DEFAULT_MODEL as OPENAI_DEFAULT_MODEL
from app.ai.llm_gateway.openai_adapter import OpenAIAdapter
from app.ai.llm_gateway.openrouter_adapter import DEFAULT_MODEL as OPENROUTER_DEFAULT_MODEL
from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter
from app.core.config import get_settings


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    model_name: str
    gateway_factory: type[LLMGateway]
    required_setting: str  # tên field trong Settings phải có giá trị thì model này mới dùng được


AVAILABLE_MODELS: list[ModelOption] = [
    ModelOption(
        id="groq-llama-3.3-70b",
        label="Groq Llama 3.3 70B",
        model_name=GROQ_DEFAULT_MODEL,
        gateway_factory=GroqAdapter,
        required_setting="groq_api_key",
    ),
    ModelOption(
        id="gemini-3.6-flash",
        label="Gemini 3.6 Flash",
        model_name=GEMINI_DEFAULT_MODEL,
        gateway_factory=GeminiAdapter,
        required_setting="gemini_api_key",
    ),
    ModelOption(
        id="claude-sonnet-5",
        label="Claude Sonnet 5",
        model_name=ANTHROPIC_DEFAULT_MODEL,
        gateway_factory=AnthropicAdapter,
        required_setting="anthropic_api_key",
    ),
    ModelOption(
        id="gpt-5.6",
        label="GPT-5.6",
        model_name=OPENAI_DEFAULT_MODEL,
        gateway_factory=OpenAIAdapter,
        required_setting="openai_api_key",
    ),
]

DEFAULT_MODEL_ID = AVAILABLE_MODELS[0].id


def get_available_models() -> list[ModelOption]:
    """Include the configured OpenRouter primary and fallback models in the chat menu."""
    settings = get_settings()
    model_names = dict.fromkeys([
        settings.openrouter_model or OPENROUTER_DEFAULT_MODEL,
        *settings.openrouter_fallback_models,
    ])
    return [
        *AVAILABLE_MODELS,
        *[
            ModelOption(
                id=f"openrouter:{name}",
                label=f"OpenRouter · {name}",
                model_name=name,
                gateway_factory=OpenRouterAdapter,
                required_setting="openrouter_api_key",
            )
            for name in model_names if name
        ],
    ]


def is_configured(option: ModelOption) -> bool:
    return bool(getattr(get_settings(), option.required_setting, None))


def resolve_model(model_id: str | None) -> ModelOption:
    """Trả về ModelOption khớp `model_id`; model_id không hợp lệ hoặc rỗng -> model mặc định."""
    return next(
        (option for option in get_available_models() if option.id == model_id),
        AVAILABLE_MODELS[0],
    )


def build_gateway(option: ModelOption) -> LLMGateway:
    return option.gateway_factory()
