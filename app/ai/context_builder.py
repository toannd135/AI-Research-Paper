"""Dedup, sort, cắt context theo token limit."""

from app.core.config import get_settings
from app.core.schemas import Citation, ScoredChunk


def _approx_tokens(text: str) -> int:
    # ~4 ký tự/token, ước lượng nhanh để tránh thêm dependency tokenizer riêng.
    return max(1, len(text) // 4)


def build_context(chunks: list[ScoredChunk], token_limit: int | None = None) -> tuple[str, list[Citation]]:
    """Dedup theo chunk id, sort theo score giảm dần, cắt tới token_limit; trả về (context_text, citations)."""
    limit = token_limit or get_settings().context_token_limit

    seen: set[str] = set()
    deduped: list[ScoredChunk] = []
    for item in sorted(chunks, key=lambda s: s.score, reverse=True):
        if item.chunk.id in seen:
            continue
        seen.add(item.chunk.id)
        deduped.append(item)

    parts: list[str] = []
    citations: list[Citation] = []
    used_tokens = 0

    for item in deduped:
        chunk = item.chunk
        tokens = _approx_tokens(chunk.text)
        if parts and used_tokens + tokens > limit:
            break
        used_tokens += tokens

        tag = f"[{len(citations) + 1}]"
        parts.append(f"{tag} (paper={chunk.paper_id}, page={chunk.page}, section={chunk.section})\n{chunk.text}")
        citations.append(
            Citation(
                paper_id=chunk.paper_id,
                chunk_id=chunk.id,
                page=chunk.page,
                section=chunk.section,
                text_snippet=chunk.text[:300],
            )
        )

        if used_tokens >= limit:
            break

    return "\n\n".join(parts), citations
