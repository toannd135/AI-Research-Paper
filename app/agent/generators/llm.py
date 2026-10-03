"""LLM Answer Generator adapter (chuẩn bị cho Tuần 2 tích hợp LLM thật)."""

from __future__ import annotations

from app.core.schemas import Chunk, Citation


class LLMAnswerGenerator:
    """Adapter tích hợp với LLM Gateway (OpenAI / Anthropic / vLLM) trong Tuần 2."""

    def __init__(
        self, model_name: str = "gpt-4o-mini", api_key: str | None = None
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key

    def generate(
        self,
        question: str,
        evidence: list[Chunk],
    ) -> tuple[str, list[Citation]]:
        """Sinh câu trả lời qua LLM Gateway với structured output."""
        # Khung interface placeholder cho Tuần 2
        raise NotImplementedError(
            "LLMAnswerGenerator sẽ được tích hợp với LLM Gateway ở Tuần 2. "
            "Vui lòng sử dụng MockAnswerGenerator ở Tuần 1 để chạy offline."
        )
