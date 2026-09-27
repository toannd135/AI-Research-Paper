"""Adapter Google Gemini."""

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.ai.llm_gateway.base import LLMGateway, LLMGatewayError, LLMResponse, Message
from app.ai.llm_gateway.retry import call_with_retry
from app.core.config import get_settings

DEFAULT_MODEL = "gemini-3.6-flash"

_ROLE_MAP = {"user": "user", "assistant": "model"}


class GeminiAdapter(LLMGateway):
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or get_settings().gemini_api_key
        if not key:
            raise LLMGatewayError("Thiếu GEMINI_API_KEY trong .env")
        self._client = genai.Client(api_key=key)

    def generate(self, messages: list[Message], model_name: str = DEFAULT_MODEL) -> LLMResponse:
        return call_with_retry(lambda: self._call_once(messages, model_name))

    def _call_once(self, messages: list[Message], model_name: str) -> LLMResponse:
        system_instruction = "\n".join(m.content for m in messages if m.role == "system") or None
        contents = [
            types.Content(role=_ROLE_MAP.get(m.role, "user"), parts=[types.Part.from_text(text=m.content)])
            for m in messages
            if m.role != "system"
        ]

        try:
            response = self._client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=system_instruction),
            )
        except genai_errors.APIError as exc:
            raise LLMGatewayError(f"Gemini API lỗi: {exc}") from exc
        except Exception as exc:  # timeout, network, SDK khác...
            raise LLMGatewayError(f"Gọi Gemini API thất bại: {exc}") from exc

        if not response.text:
            raise LLMGatewayError("Gemini trả về response rỗng")

        return LLMResponse(text=response.text, model=model_name)
