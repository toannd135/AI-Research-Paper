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


class LLMGateway(ABC):
    @abstractmethod
    def generate(self, messages: list[Message], model_name: str) -> LLMResponse:
        """Gửi messages tới LLM, trả về câu trả lời. Raise LLMGatewayError khi lỗi."""
        raise NotImplementedError
