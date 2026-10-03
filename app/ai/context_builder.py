"""Dedup, sort, cắt context theo token limit."""

from app.core.config import get_settings
from app.core.schemas import Citation, ScoredChunk


def _approx_tokens(text: str) -> int:
    # ~3 ký tự/token (ước lượng an toàn cho tiếng Việt UTF-8 và thuật ngữ kỹ thuật)
    return max(1, int(len(text) / 3.0))


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

        # Nếu ngay chunk đầu tiên đã vượt quá token limit, cắt ngắn text của nó để không làm tràn context
        text_to_include = chunk.text
        if tokens > limit:
            char_limit = limit * 3
            text_to_include = chunk.text[:char_limit] + "\n... [đã cắt bớt để đảm bảo giới hạn token]"
            tokens = limit

        used_tokens += tokens

        tag = f"[{len(citations) + 1}]"
        parts.append(f"{tag} (paper={chunk.paper_id}, page={chunk.page}, section={chunk.section})\n{text_to_include}")
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
