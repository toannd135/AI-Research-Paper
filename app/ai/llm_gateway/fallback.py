"""Gateway dự phòng: khi provider chính bị rate limit (429) thì gọi lại trên provider phụ."""

import logging

from app.ai.llm_gateway.base import LLMGateway, LLMRateLimitError, LLMResponse, Message

logger = logging.getLogger(__name__)


class FallbackGateway(LLMGateway):
    """Thử `primary`; chỉ khi gặp LLMRateLimitError thì chuyển sang `fallback` với `fallback_model`.

    Các lỗi khác (auth, timeout, response rỗng...) được raise nguyên trạng, không chuyển provider.
    """

    def __init__(self, primary: LLMGateway, fallback: LLMGateway, fallback_model: str) -> None:
        self._primary = primary
        self._fallback = fallback
        self._fallback_model = fallback_model

    def generate(self, messages: list[Message], model_name: str) -> LLMResponse:
        try:
            return self._primary.generate(messages, model_name)
        except LLMRateLimitError:
            logger.warning(
                "Provider chính bị rate limit với model %s, chuyển sang model dự phòng %s",
                model_name,
                self._fallback_model,
            )
            return self._fallback.generate(messages, self._fallback_model)
