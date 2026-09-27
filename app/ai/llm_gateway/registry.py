"""Danh sách model user có thể chọn ở chat UI — map model id (client gửi lên) -> adapter thật."""

from dataclasses import dataclass

from app.ai.llm_gateway.anthropic_adapter import DEFAULT_MODEL as ANTHROPIC_DEFAULT_MODEL
from app.ai.llm_gateway.anthropic_adapter import AnthropicAdapter
from app.ai.llm_gateway.base import LLMGateway
from app.ai.llm_gateway.gemini_adapter import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL
from app.ai.llm_gateway.gemini_adapter import GeminiAdapter
from app.ai.llm_gateway.openai_adapter import DEFAULT_MODEL as OPENAI_DEFAULT_MODEL
from app.ai.llm_gateway.openai_adapter import OpenAIAdapter
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

_BY_ID = {option.id: option for option in AVAILABLE_MODELS}
DEFAULT_MODEL_ID = AVAILABLE_MODELS[0].id


def is_configured(option: ModelOption) -> bool:
    return bool(getattr(get_settings(), option.required_setting, None))


def resolve_model(model_id: str | None) -> ModelOption:
    """Trả về ModelOption khớp `model_id`; model_id không hợp lệ hoặc rỗng -> model mặc định."""
    return _BY_ID.get(model_id or DEFAULT_MODEL_ID, AVAILABLE_MODELS[0])


def build_gateway(option: ModelOption) -> LLMGateway:
    return option.gateway_factory()
