"""Protocol definition cho AnswerGenerator abstraction."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.schemas import Chunk, Citation


@runtime_checkable
class AnswerGenerator(Protocol):
    """Protocol trừu tượng cho tầng sinh câu trả lời kèm trích dẫn."""

    def generate(
        self,
        question: str,
        evidence: list[Chunk],
    ) -> tuple[str, list[Citation]]:
        """Sinh câu trả lời tổng hợp và danh sách Citation từ tập bằng chứng.

        Args:
            question: Câu hỏi nghiên cứu của người dùng.
            evidence: Danh sách các đoạn văn bản (chunks) đã được trích xuất.

        Returns:
            tuple gồm (answer_text, list_of_citations).
        """
        ...
