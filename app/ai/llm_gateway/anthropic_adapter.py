"""Adapter Anthropic (Claude)."""

import anthropic

from app.ai.llm_gateway.base import LLMGateway, LLMGatewayError, LLMResponse, Message
from app.ai.llm_gateway.retry import call_with_retry
from app.core.config import get_settings

DEFAULT_MODEL = "claude-sonnet-5"
_MAX_OUTPUT_TOKENS = 4096


class AnthropicAdapter(LLMGateway):
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or get_settings().anthropic_api_key
        if not key:
            raise LLMGatewayError("Thiếu ANTHROPIC_API_KEY trong .env")
        self._client = anthropic.Anthropic(api_key=key)

    def generate(self, messages: list[Message], model_name: str = DEFAULT_MODEL) -> LLMResponse:
        return call_with_retry(lambda: self._call_once(messages, model_name))

    def _call_once(self, messages: list[Message], model_name: str) -> LLMResponse:
        system = "\n".join(m.content for m in messages if m.role == "system") or None
        conversation = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

        try:
            response = self._client.messages.create(
                model=model_name,
                system=system,
                messages=conversation,
                max_tokens=_MAX_OUTPUT_TOKENS,
            )
        except anthropic.APIError as exc:
            raise LLMGatewayError(f"Anthropic API lỗi: {exc}") from exc
        except Exception as exc:  # timeout, network, SDK khác...
            raise LLMGatewayError(f"Gọi Anthropic API thất bại: {exc}") from exc

        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        if not text:
            raise LLMGatewayError("Anthropic trả về response rỗng")

        return LLMResponse(text=text, model=model_name)
