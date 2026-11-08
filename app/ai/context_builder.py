"""Dedup, sort, cắt context theo token limit."""

from app.core.config import get_settings
from app.core.schemas import Citation, ScoredChunk


def _approx_tokens(text: str) -> int:
    # ~3 ký tự/token (ước lượng an toàn cho tiếng Việt UTF-8 và thuật ngữ kỹ thuật)
    return max(1, int(len(text) / 3.0))


def _diversify(items: list[ScoredChunk]) -> list[ScoredChunk]:
    """Chunk tốt nhất của mỗi paper đứng trước, các chunk phụ sau: context phủ được nhiều paper nhất có thể."""
    seen_papers: set[str] = set()
    first: list[ScoredChunk] = []
    rest: list[ScoredChunk] = []
    for item in items:  # đã sort theo score giảm dần
        if item.chunk.paper_id in seen_papers:
            rest.append(item)
        else:
            seen_papers.add(item.chunk.paper_id)
            first.append(item)
    return first + rest


MIN_PAPER_TOKENS = 150  # chunk đầu của một paper không cắt ngắn hơn mức này (dưới mức này đoạn trích mất nghĩa)


def _fit_first_chunks(items: list[ScoredChunk], limit: int) -> dict[str, str]:
    """Khi chunk tốt nhất của mọi paper cộng lại vượt `limit`: chia đều ngân sách cho từng paper và cắt ngắn
    chunk đầu theo ranh giới từ, để context chứa đủ mọi paper (kho nhỏ phải cite hết). Trả về {chunk_id: text đã cắt}."""
    firsts: dict[str, ScoredChunk] = {}
    for item in items:
        firsts.setdefault(item.chunk.paper_id, item)
    if sum(_approx_tokens(i.chunk.text) for i in firsts.values()) <= limit:
        return {}
    budget_chars = max(MIN_PAPER_TOKENS, limit // len(firsts)) * 3
    trimmed: dict[str, str] = {}
    for item in firsts.values():
        text = item.chunk.text
        if len(text) > budget_chars:
            cut = text[:budget_chars]
            trimmed[item.chunk.id] = (cut.rsplit(None, 1)[0] if " " in cut else cut) + " …"
    return trimmed


def build_context(
    chunks: list[ScoredChunk], token_limit: int | None = None, diversify: bool = False
) -> tuple[str, list[Citation]]:
    """Dedup theo chunk id, sort theo score giảm dần, cắt tới token_limit; trả về (context_text, citations).

    diversify=True: ưu tiên mỗi paper một chunk tốt nhất trước khi lấy chunk thứ hai (dùng cho bài tổng hợp nhiều nguồn);
    nếu chunk đầu của mọi paper không vừa limit thì cắt ngắn chúng theo ngân sách chia đều để không paper nào bị loại.
    """
    limit = token_limit or get_settings().context_token_limit

    seen: set[str] = set()
    deduped: list[ScoredChunk] = []
    for item in sorted(chunks, key=lambda s: s.score, reverse=True):
        if item.chunk.id in seen:
            continue
        seen.add(item.chunk.id)
        deduped.append(item)
    trimmed: dict[str, str] = {}
    if diversify:
        deduped = _diversify(deduped)
        trimmed = _fit_first_chunks(deduped, limit)

    parts: list[str] = []
    citations: list[Citation] = []
    used_tokens = 0

    for item in deduped:
        chunk = item.chunk
        text_to_include = trimmed.get(chunk.id, chunk.text)
        tokens = _approx_tokens(text_to_include)
        if parts and used_tokens + tokens > limit:
            break

        # Nếu ngay chunk đầu tiên đã vượt quá token limit, cắt ngắn text của nó để không làm tràn context
        if tokens > limit:
            char_limit = limit * 3
            text_to_include = text_to_include[:char_limit] + "\n... [đã cắt bớt để đảm bảo giới hạn token]"
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
