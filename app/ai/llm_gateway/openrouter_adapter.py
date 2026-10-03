"""Adapter OpenRouter.ai (truy cập hơn 200+ models bao gồm Nemotron, Gemma, Qwen, Claude, GPT)."""

import json
from typing import Any

import httpx

from app.ai.llm_gateway.base import LLMGateway, LLMGatewayError, LLMResponse, Message
from app.ai.llm_gateway.retry import call_with_retry
from app.core.config import get_settings

DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_FALLBACK_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "qwen/qwen3.8-27b:free",
]
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterAdapter(LLMGateway):
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = OPENROUTER_BASE_URL,
        fallback_models: list[str] | None = None,
    ) -> None:
        settings = get_settings()
        key = api_key or settings.openrouter_api_key
        if not key:
            raise LLMGatewayError("Thiếu OPENROUTER_API_KEY trong .env")
        self._api_key = key
        self._base_url = base_url.rstrip("/")
        self._fallback_models = fallback_models or getattr(settings, "openrouter_fallback_models", None) or DEFAULT_FALLBACK_MODELS

    def generate(self, messages: list[Message], model_name: str = DEFAULT_MODEL) -> LLMResponse:
        return call_with_retry(lambda: self._call_once(messages, model_name))

    def _call_once(self, messages: list[Message], model_name: str) -> LLMResponse:
        conversation = [{"role": m.role, "content": m.content} for m in messages]
        chosen_model = model_name or DEFAULT_MODEL

        # Tạo danh sách ưu tiên: model được yêu cầu đứng đầu, sau đó là danh sách fallback
        model_candidates = [chosen_model]
        for m in self._fallback_models:
            if m not in model_candidates:
                model_candidates.append(m)

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://github.com/paperai",
            "X-Title": "PaperAI",
            "Content-Type": "application/json",
        }

        # OpenRouter hỗ trợ tính năng truyền danh sách models để tự động fallback khi model chính quá tải
        payload = {
            "models": model_candidates,
            "messages": conversation,
            "temperature": 0.3,
        }

        try:
            with httpx.Client(timeout=90.0) as client:
                res = client.post(url, headers=headers, json=payload)

                if res.status_code == 401:
                    raise LLMGatewayError(f"OpenRouter API Key không hợp lệ: {res.text}")

                if res.status_code != 200:
                    raise LLMGatewayError(f"OpenRouter API returned HTTP {res.status_code}: {res.text}")

                data = res.json()

                # Kiểm tra lỗi trong payload JSON (OpenRouter có thể trả HTTP 200 kèm error dict)
                if "error" in data:
                    err_msg = data["error"].get("message", str(data["error"]))
                    raise LLMGatewayError(f"OpenRouter upstream error: {err_msg}")

                choices = data.get("choices", [])
                if not choices:
                    raise LLMGatewayError(f"OpenRouter trả về response rỗng: {res.text}")

                message = choices[0].get("message", {})
                text = message.get("content", "")
                if not text:
                    raise LLMGatewayError("OpenRouter trả về content rỗng")

                resolved_model = data.get("model", chosen_model)
                return LLMResponse(text=text, model=resolved_model)

        except LLMGatewayError:
            raise
        except Exception as exc:
            raise LLMGatewayError(f"Gọi OpenRouter API thất bại: {exc}") from exc
