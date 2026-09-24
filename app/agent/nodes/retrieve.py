"""Node trích xuất bằng chứng từ các bài báo đã tìm thấy."""

from __future__ import annotations

from app.agent.tools.retrieve_evidence import retrieve_evidence
from app.core.schemas import Chunk, ResearchState


def retrieve_node(state: ResearchState) -> dict:
    """Trích xuất evidence chunks cho các bài báo trong state.

    Bắt buộc validate kết quả thô từ tool bằng Chunk.model_validate().
    """
    question = state.get("question", "")
    papers = state.get("papers", [])

    all_chunks: list[Chunk] = []
    seen_chunk_ids: set[str] = set()

    if not papers:
        return {
            "evidence": [],
            "steps": ["retrieve"],
        }

    for paper in papers:
        raw_chunks = retrieve_evidence.invoke(
            {"query": question, "paper_id": paper.paper_id}
        )
        for raw_chunk in raw_chunks:
            chunk = Chunk.model_validate(raw_chunk)
            if chunk.chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk.chunk_id)
                all_chunks.append(chunk)

    return {
        "evidence": all_chunks,
        "steps": ["retrieve"],
    }
