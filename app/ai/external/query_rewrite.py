"""Chuyển câu hỏi người dùng (mọi ngôn ngữ, có thể dài/lẫn lệnh) thành từ khóa tiếng Anh cho OpenAlex.

OpenAlex chỉ khớp từ khóa: gửi nguyên câu tiếng Việt chỉ ra bài tiếng Việt, còn câu dài ra 0 kết quả.
"""

import logging
from functools import lru_cache

from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.default import get_default_agent_gateway

logger = logging.getLogger(__name__)

_MAX_PLAIN_CHARS = 120  # câu ASCII ngắn hơn mức này coi như từ khóa tiếng Anh, không cần gọi LLM
_MAX_QUERY_CHARS = 200

_SYSTEM_PROMPT = (
    "Convert the user's research request (any language) into ONE English academic search query for the "
    "OpenAlex paper database: 3-8 core technical keywords/phrases, standard English terminology, correct any "
    "typos, drop instructions such as 'write a paper about' and all formatting requirements. "
    "Output only the query text, no quotes, no explanation."
)


def _clean(text: str) -> str:
    return " ".join(text.replace("*", " ").replace('"', " ").split())


@lru_cache(maxsize=256)
def _rewrite(query: str) -> str:
    gateway, model_name = get_default_agent_gateway()
    return _ask(gateway, model_name, query)


def _ask(gateway: LLMGateway, model_name: str | None, query: str) -> str:
    response = gateway.generate(
        messages=[Message(role="system", content=_SYSTEM_PROMPT), Message(role="user", content=query[:2000])],
        model_name=model_name,
    )
    lines = [ln for ln in response.text.strip().splitlines() if ln.strip()]
    return _clean(lines[0])[:_MAX_QUERY_CHARS] if lines else ""


def to_english_search_query(query: str, gateway: LLMGateway | None = None, model_name: str | None = None) -> str:
    """Từ khóa tiếng Anh để tìm paper quốc tế; lỗi LLM thì dùng lại câu gốc đã làm sạch (không làm hỏng tìm kiếm)."""
    cleaned = _clean(query)
    if len(cleaned) <= _MAX_PLAIN_CHARS and cleaned.isascii():
        return cleaned
    try:
        rewritten = _ask(gateway, model_name, cleaned) if gateway else _rewrite(cleaned)
    except Exception:
        logger.warning("Không viết lại được truy vấn OpenAlex, dùng câu gốc", exc_info=True)
        return cleaned[:_MAX_QUERY_CHARS]
    return rewritten or cleaned[:_MAX_QUERY_CHARS]
