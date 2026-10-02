"""Adapter Groq Cloud (hỗ trợ gọi endpoint Groq qua HTTPX / OpenAI API tương thích)."""

import json
from typing import Any

try:
    import openai
except ImportError:
    openai = None  # type: ignore

import httpx

from app.ai.llm_gateway.base import LLMGateway, LLMGatewayError, LLMResponse, Message
from app.ai.llm_gateway.retry import call_with_retry
from app.core.config import get_settings

DEFAULT_MODEL = "openai/gpt-oss-120b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
KNOWN_TEXT_MODELS = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
]


class GroqAdapter(LLMGateway):
    def __init__(self, api_key: str | None = None, base_url: str = GROQ_BASE_URL) -> None:
        key = api_key or get_settings().groq_api_key
        if not key:
            raise LLMGatewayError("Thiếu GROQ_API_KEY trong .env")
        self._api_key = key
        self._base_url = base_url.rstrip("/")

        if openai is not None:
            try:
                self._client = openai.OpenAI(api_key=key, base_url=base_url)
            except Exception:
                self._client = None
        else:
            self._client = None

    def generate(self, messages: list[Message], model_name: str = DEFAULT_MODEL) -> LLMResponse:
        return call_with_retry(lambda: self._call_once(messages, model_name))

    def _fit_context_window(self, messages: list[dict[str, str]], max_chars: int = 18000) -> list[dict[str, str]]:
        """Đảm bảo tổng độ dài input prompt luôn nằm an toàn trong giới hạn 8k token (~18,000 ký tự)."""
        total_chars = sum(len(m.get("content", "")) for m in messages)
        if total_chars <= max_chars:
            return messages

        excess = total_chars - max_chars
        longest_idx = max(range(len(messages)), key=lambda i: len(messages[i].get("content", "")))
        longest_content = messages[longest_idx].get("content", "")
        keep_len = max(300, len(longest_content) - excess - 100)

        trimmed = [dict(m) for m in messages]
        trimmed[longest_idx]["content"] = (
            longest_content[:keep_len]
            + "\n\n... [Đã tự động cắt bớt để đảm bảo giới hạn token đầu vào của model]"
        )
        return trimmed

    def _call_once(self, messages: list[Message], model_name: str) -> LLMResponse:
        raw_conversation = [{"role": m.role, "content": m.content} for m in messages]
        conversation = self._fit_context_window(raw_conversation)
        chosen_model = model_name or DEFAULT_MODEL

        # Cách 1: Sử dụng OpenAI SDK nếu sẵn sàng
        if self._client is not None:
            try:
                response = self._client.chat.completions.create(
                    model=chosen_model,
                    messages=conversation,
                    temperature=0.3,
                )
                text = response.choices[0].message.content if response.choices else None
                if not text:
                    raise LLMGatewayError("Groq Cloud trả về response rỗng")
                return LLMResponse(text=text, model=chosen_model)
            except Exception as exc:
                err_str = str(exc)
                if "401" in err_str or "Authentication" in err_str:
                    raise LLMGatewayError(f"Groq Cloud API Key không hợp lệ: {exc}") from exc
                if "404" in err_str or "model_not_found" in err_str:
                    fallback_model = self._find_fallback_model()
                    if fallback_model and fallback_model != chosen_model:
                        return self._call_via_httpx(conversation, fallback_model)

        # Cách 2: Direct HTTPX call đến https://api.groq.com/openai/v1/chat/completions
        return self._call_via_httpx(conversation, chosen_model)

    def _call_via_httpx(self, conversation: list[dict[str, str]], chosen_model: str) -> LLMResponse:
        try:
            url = f"{self._base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": chosen_model,
                "messages": conversation,
                "temperature": 0.3,
            }
            with httpx.Client(timeout=60.0) as client:
                res = client.post(url, headers=headers, json=payload)
                if res.status_code == 404 or "model_not_found" in res.text:
                    fallback_model = self._find_fallback_model()
                    if fallback_model and fallback_model != chosen_model:
                        payload["model"] = fallback_model
                        res = client.post(url, headers=headers, json=payload)
                        chosen_model = fallback_model
                if res.status_code != 200:
                    raise LLMGatewayError(f"Groq API returned HTTP {res.status_code}: {res.text}")
                data = res.json()
                choices = data.get("choices", [])
                if not choices:
                    raise LLMGatewayError(f"Groq Cloud trả về response rỗng: {res.text}")
                text = choices[0].get("message", {}).get("content", "")
                if not text:
                    raise LLMGatewayError("Groq Cloud trả về response rỗng")
                return LLMResponse(text=text, model=chosen_model)
        except LLMGatewayError:
            raise
        except Exception as exc:
            raise LLMGatewayError(f"Gọi Groq Cloud API qua HTTPX thất bại: {exc}") from exc

    def _find_fallback_model(self) -> str | None:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                if res.status_code == 200:
                    available = [m.get("id") for m in res.json().get("data", [])]
                    for candidate in KNOWN_TEXT_MODELS:
                        if candidate in available:
                            return candidate
                    if available:
                        return available[0]
        except Exception:
            pass
        return "openai/gpt-oss-120b"

