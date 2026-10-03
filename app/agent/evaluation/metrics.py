"""Recall@K, faithfulness, task success rate."""

from app.agent.evidence.citation_validator import find_invalid_citations
from app.core.schemas import Citation


def recall_at_k(retrieved_chunk_ids: list[str], relevant_chunk_ids: list[str]) -> float:
    """Tỉ lệ chunk liên quan (gold) xuất hiện trong top-K kết quả retrieval."""
    if not relevant_chunk_ids:
        return 0.0
    retrieved = set(retrieved_chunk_ids)
    hits = sum(1 for cid in relevant_chunk_ids if cid in retrieved)
    return hits / len(relevant_chunk_ids)


def citation_faithfulness(report: str, citations: list[Citation]) -> float:
    """Tỉ lệ trích dẫn [n] trong report hợp lệ (khớp với danh sách citations thật)."""
    import re

    used = {int(m) for m in re.findall(r"\[(\d+)\]", report)}
    if not used:
        return 1.0
    invalid = set(find_invalid_citations(report, citations))
    return 1 - (len(invalid) / len(used))
