"""Danh sách model user có thể chọn ở chat UI — map model id (client gửi lên) -> adapter thật."""

from collections.abc import Callable
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
from app.ai.llm_gateway.openrouter_adapter import (
    DEFAULT_MODEL as OPENROUTER_DEFAULT_MODEL,
)
from app.ai.llm_gateway.openrouter_adapter import OpenRouterAdapter
from app.core.config import get_settings


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    model_name: str  # model mặc định, dùng khi model_name_setting không có giá trị
    gateway_factory: Callable[[], LLMGateway]
    required_setting: str  # tên field trong Settings phải có giá trị thì model này mới dùng được
    # Tên field trong Settings cho phép đổi model qua .env (vd OPENROUTER_MODEL, GROQ_MODEL).
    model_name_setting: str | None = None


def _gemma_gateway(key_attr: str) -> Callable[[], LLMGateway]:
    """OpenRouterAdapter dùng key riêng của từng model Gemma."""
    return lambda: OpenRouterAdapter(api_key=getattr(get_settings(), key_attr))


AVAILABLE_MODELS: list[ModelOption] = [
    ModelOption(
        id="openrouter",
        label="OpenRouter",
        model_name=OPENROUTER_DEFAULT_MODEL,
        gateway_factory=OpenRouterAdapter,
        required_setting="openrouter_api_key",
        model_name_setting="openrouter_model",
    ),
    ModelOption(
        id="gemma-4-31b-it-free",
        label="OpenRouter Gemma 4 31B",
        model_name="google/gemma-4-31b-it:free",
        gateway_factory=_gemma_gateway("gemma_31b_api_key"),
        required_setting="gemma_31b_api_key",
        model_name_setting="model_gemma_4_31b_it_free",
    ),
    ModelOption(
        id="gemma-4-26b-a4b-free",
        label="OpenRouter Gemma 4 26B A4B",
        model_name="google/gemma-4-26b-a4b:free",
        gateway_factory=_gemma_gateway("gemma_26b_api_key"),
        required_setting="gemma_26b_api_key",
        model_name_setting="model_gemma_4_26b_a4b_free",
    ),
    ModelOption(
        id="groq-gpt-oss-120b",
        label="Groq",
        model_name=GROQ_DEFAULT_MODEL,
        gateway_factory=GroqAdapter,
        required_setting="groq_api_key",
        model_name_setting="groq_model",
    ),
    ModelOption(
        id="gemini-3.6-flash",
        label="Google · Gemini 3.6 Flash",
        model_name=GEMINI_DEFAULT_MODEL,
        gateway_factory=GeminiAdapter,
        required_setting="gemini_api_key",
    ),
    ModelOption(
        id="claude-sonnet-5",
        label="Anthropic",
        model_name=ANTHROPIC_DEFAULT_MODEL,
        gateway_factory=AnthropicAdapter,
        required_setting="anthropic_api_key",
        model_name_setting="anthropic_model",
    ),
    ModelOption(
        id="gpt-5.6",
        label="OpenAI",
        model_name=OPENAI_DEFAULT_MODEL,
        gateway_factory=OpenAIAdapter,
        required_setting="openai_api_key",
        model_name_setting="openai_model",
    ),
]

_BY_ID = {option.id: option for option in AVAILABLE_MODELS}
DEFAULT_MODEL_ID = AVAILABLE_MODELS[0].id


def is_configured(option: ModelOption) -> bool:
    return bool(getattr(get_settings(), option.required_setting, None))


def resolve_model_name(option: ModelOption) -> str:
    """Tên model thực tế gửi lên provider: ưu tiên giá trị cấu hình trong .env, không có thì dùng mặc định."""
    if option.model_name_setting:
        configured = getattr(get_settings(), option.model_name_setting, None)
        if configured:
            return configured
    return option.model_name


def label_for(option: ModelOption) -> str:
    """Nhãn hiển thị kèm tên model thực tế, để người dùng biết chính xác model nào đang chạy."""
    name = resolve_model_name(option)
    return f"{option.label} · {name}" if option.model_name_setting else option.label


def resolve_model(model_id: str | None) -> ModelOption:
    """Trả về ModelOption khớp `model_id`; model_id không hợp lệ hoặc rỗng -> model mặc định."""
    return _BY_ID.get(model_id or DEFAULT_MODEL_ID, AVAILABLE_MODELS[0])


def build_gateway(option: ModelOption) -> LLMGateway:
    return option.gateway_factory()
