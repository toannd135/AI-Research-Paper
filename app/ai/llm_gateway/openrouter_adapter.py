"""Adapter OpenRouter.ai (truy cập hơn 200+ models bao gồm Nemotron, Gemma, Qwen, Claude, GPT)."""

import httpx

from app.ai.llm_gateway.base import LLMGateway, LLMGatewayError, LLMRateLimitError, LLMResponse, Message
from app.ai.llm_gateway.retry import call_with_retry
from app.core.config import get_settings

# Chờ model trả lời tối đa 15 phút (model free hay xếp hàng); kết nối/ghi vẫn giới hạn ngắn để lỗi mạng báo sớm.
_HTTP_TIMEOUT = httpx.Timeout(900.0, connect=15.0, write=60.0, pool=15.0)
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_FALLBACK_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "qwen/qwen3.8-27b:free",
]
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_MODELS_PER_REQUEST = 3


def _extract_text(content) -> str:
    """Lấy text từ content: chuỗi thường hoặc mảng part [{type: text, text: ...}]."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        return "".join(parts).strip()
    return ""


def _parse_retry_after(headers) -> float | None:
    """Đọc header Retry-After (giây). Trả None nếu thiếu hoặc không phải số."""
    try:
        raw = headers.get("retry-after") if headers else None
        return float(raw) if raw else None
    except (TypeError, ValueError, AttributeError):
        return None


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
        chosen_model = model_name or DEFAULT_MODEL

        # Tạo danh sách ưu tiên: model được yêu cầu đứng đầu, sau đó là danh sách fallback
        model_candidates = [chosen_model]
        for m in self._fallback_models:
            if m not in model_candidates:
                model_candidates.append(m)

        # Model reasoning (vd. Nemotron) đôi khi trả HTTP 200 nhưng content rỗng (đáp án nằm trong
        # "reasoning" hoặc hết token). Gửi lại cùng danh sách sẽ lại trúng model đó, nên loại nó ra
        # và thử model kế tiếp.
        empty_error: LLMGatewayError | None = None
        while model_candidates:
            # OpenRouter từ chối mảng "models" dài hơn 3 phần tử (HTTP 400).
            batch = model_candidates[:MAX_MODELS_PER_REQUEST]
            try:
                return self._post(messages, batch)
            except _EmptyContentError as exc:
                empty_error = exc
                bad_model = exc.model if exc.model in model_candidates else batch[0]
                model_candidates.remove(bad_model)
        raise empty_error or LLMGatewayError("OpenRouter trả về content rỗng")

    def _post(self, messages: list[Message], models: list[str]) -> LLMResponse:
        conversation = [{"role": m.role, "content": m.content} for m in messages]
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://github.com/paperai",
            "X-Title": "PaperAI",
            "Content-Type": "application/json",
        }

        # OpenRouter hỗ trợ tính năng truyền danh sách models để tự động fallback khi model chính quá tải
        payload = {
            "models": models,
            "messages": conversation,
            "temperature": 0.3,
        }

        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                res = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise LLMGatewayError(f"Gọi OpenRouter API thất bại: {exc}") from exc

        if res.status_code == 401:
            raise LLMGatewayError(f"OpenRouter API Key không hợp lệ: {res.text}")

        if res.status_code == 429:
            raise LLMRateLimitError(
                f"OpenRouter API bị giới hạn tần suất (HTTP 429): {res.text}",
                retry_after=_parse_retry_after(res.headers),
            )

        if res.status_code != 200:
            raise LLMGatewayError(f"OpenRouter API returned HTTP {res.status_code}: {res.text}")

        try:
            data = res.json()
        except ValueError as exc:
            raise LLMGatewayError(f"OpenRouter trả về JSON không hợp lệ: {exc}") from exc

        # Kiểm tra lỗi trong payload JSON (OpenRouter có thể trả HTTP 200 kèm error dict)
        if "error" in data:
            err = data["error"]
            err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise LLMGatewayError(f"OpenRouter upstream error: {err_msg}")

        choices = data.get("choices") or []
        if not choices:
            raise LLMGatewayError(f"OpenRouter trả về response rỗng: {res.text}")

        resolved_model = data.get("model") or models[0]
        choice = choices[0]
        text = _extract_text((choice.get("message") or {}).get("content"))
        if not text:
            raise _EmptyContentError(
                f"OpenRouter trả về content rỗng (model={resolved_model}, "
                f"finish_reason={choice.get('finish_reason')})",
                model=resolved_model,
            )

        return LLMResponse(text=text, model=resolved_model)


class _EmptyContentError(LLMGatewayError):
    """Model trả HTTP 200 nhưng content rỗng — nên chuyển sang model khác."""

    def __init__(self, message: str, model: str) -> None:
        super().__init__(message)
        self.model = model
