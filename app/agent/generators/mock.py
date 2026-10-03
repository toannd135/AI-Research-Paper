"""Mock implementation của AnswerGenerator phục vụ test offline và baseline."""

from __future__ import annotations

from app.core.schemas import Chunk, Citation


class MockAnswerGenerator:
    """Mock generator sinh câu trả lời deterministic và đảm bảo 100% citation grounding."""

    def generate(
        self,
        question: str,
        evidence: list[Chunk],
    ) -> tuple[str, list[Citation]]:
        """Tổng hợp câu trả lời dựa trên bằng chứng và tạo citation nghiêm ngặt."""
        if not evidence:
            return "Không tìm thấy đủ bằng chứng để trả lời câu hỏi.", []

        citations: list[Citation] = []
        answer_parts: list[str] = [
            f"Dựa trên các nghiên cứu đã phân tích cho câu hỏi '{question}':"
        ]

        # Duyệt qua các evidence tìm được để trích xuất ý chính và sinh citation
        for idx, chunk in enumerate(evidence, start=1):
            content = chunk.content.strip()

            # Trích xuất 1 câu hoặc 1 đoạn substring thực tế từ chunk.content để làm quoted_text
            # Đảm bảo 100% quoted_text là chuỗi con (substring) có trong chunk.content
            if "." in content:
                first_sentence = content.split(".")[0].strip()
                quoted_text = first_sentence
            else:
                quoted_text = content[:100].strip()

            # Xác thực đảm bảo chuỗi con
            if quoted_text not in chunk.content:
                quoted_text = chunk.content  # fallback an toàn luôn luôn là substring

            citation = Citation(
                chunk_id=chunk.chunk_id,
                paper_id=chunk.paper_id,
                page_number=chunk.page_number,
                quoted_text=quoted_text,
            )
            citations.append(citation)

            sec_info = f" ({chunk.section_title})" if chunk.section_title else ""
            answer_parts.append(
                f"- Theo nghiên cứu [{chunk.paper_id}]{sec_info}, trang {chunk.page_number}: {quoted_text}."
            )

        answer = "\n".join(answer_parts)
        return answer, citations
