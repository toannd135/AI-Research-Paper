"""Parse JSON từ text trả về của LLM (có thể kèm ```json fences)."""

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_llm_json(text: str) -> dict | list | None:
    """Trả về object JSON parse được từ response LLM, hoặc None nếu không parse được."""
    match = _FENCE_RE.search(text)
    candidate = match.group(1) if match else text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
