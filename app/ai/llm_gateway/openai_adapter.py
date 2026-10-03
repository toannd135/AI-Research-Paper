"""Adapter OpenAI."""

import openai

from app.ai.llm_gateway.base import LLMGateway, LLMGatewayError, LLMResponse, Message
from app.ai.llm_gateway.retry import call_with_retry
from app.core.config import get_settings

DEFAULT_MODEL = "gpt-5.6"


class OpenAIAdapter(LLMGateway):
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or get_settings().openai_api_key
        if not key:
            raise LLMGatewayError("Thiếu OPENAI_API_KEY trong .env")
        self._client = openai.OpenAI(api_key=key)

    def generate(self, messages: list[Message], model_name: str = DEFAULT_MODEL) -> LLMResponse:
        return call_with_retry(lambda: self._call_once(messages, model_name))

    def _call_once(self, messages: list[Message], model_name: str) -> LLMResponse:
        conversation = [{"role": m.role, "content": m.content} for m in messages]

        try:
            response = self._client.chat.completions.create(model=model_name, messages=conversation)
        except openai.APIError as exc:
            raise LLMGatewayError(f"OpenAI API lỗi: {exc}") from exc
        except Exception as exc:  # timeout, network, SDK khác...
            raise LLMGatewayError(f"Gọi OpenAI API thất bại: {exc}") from exc

        text = response.choices[0].message.content if response.choices else None
        if not text:
            raise LLMGatewayError("OpenAI trả về response rỗng")

        return LLMResponse(text=text, model=model_name)
