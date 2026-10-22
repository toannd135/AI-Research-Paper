"""Interface generate(messages, model_name)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    text: str
    model: str


class LLMGatewayError(Exception):
    """Lỗi khi gọi LLM provider (rate limit, timeout, auth, response rỗng...)."""


class LLMRateLimitError(LLMGatewayError):
    """Provider trả 429; `retry_after` (giây) lấy từ header Retry-After nếu có."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMGateway(ABC):
    @abstractmethod
    def generate(self, messages: list[Message], model_name: str) -> LLMResponse:
        """Gửi messages tới LLM, trả về câu trả lời. Raise LLMGatewayError khi lỗi."""
        raise NotImplementedError
