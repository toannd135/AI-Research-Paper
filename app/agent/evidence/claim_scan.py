"""Quét báo cáo đã sinh: tìm câu khẳng định như kết quả cho claim chưa được chứng minh, rồi hạ giọng câu đó."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agent.json_utils import parse_llm_json
from app.ai.llm_gateway.base import LLMGateway, LLMGatewayError, Message

logger = logging.getLogger(__name__)

_ASSERTIVE = re.compile(
    r"\b(outperform\w*|surpass\w*|achiev(?:e|es|ed)|reduc(?:e|es|ed)|improv(?:e|es|ed)|better than|faster than|superior|"
    r"state-of-the-art|demonstrat\w+|show(?:s|ed|n)? that|significantly|novel|first to|exceed\w*|yield(?:s|ed)?)\b",
    re.IGNORECASE,
)
_HEDGE = re.compile(
    r"\b(hypothes\w+|expect\w*|anticipat\w+|aim\w*|plan\w*|would|may|might|could|potential\w*|future work|intend\w*|"
    r"remains? to be|not yet|unverified|limitation\w*|if|whether|attempt\w*|seek\w*)\b",
    re.IGNORECASE,
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9\-]{3,}")
_STOP = {"that", "with", "this", "from", "than", "have", "which", "their", "model", "method", "proposed", "results", "using"}
_SKIP_PREFIX = ("#", "|", "$", "```", "**Table", "**Figure", "- [", "[")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text)} - _STOP


def _claim_tokens(claim: dict[str, Any]) -> set[str]:
    return _tokens(" ".join(str(claim.get(k) or "") for k in ("text", "baseline", "metric", "dataset")))


def _matches(sentence_tokens: set[str], claim_tokens: set[str]) -> bool:
    if len(claim_tokens) < 2:
        return False
    need = max(2, -(-len(claim_tokens) // 2))
    return len(sentence_tokens & claim_tokens) >= need


def find_leaked_claims(report: str, claims: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Câu khẳng định (không hedge) khớp nội dung một claim `unsupported`/`hypothesis`."""
    weak = [(c, _claim_tokens(c)) for c in claims if c.get("status") in ("unsupported", "hypothesis")]
    if not weak:
        return []
    leaks: list[dict[str, str]] = []
    in_fence = False
    for line in report.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or stripped.startswith(_SKIP_PREFIX):
            continue
        for sentence in _SENT_SPLIT.split(line):
            if not _ASSERTIVE.search(sentence) or _HEDGE.search(sentence):
                continue
            tokens = _tokens(sentence)
            for claim, claim_tokens in weak:
                if _matches(tokens, claim_tokens):
                    leaks.append({"claim_id": claim["id"], "sentence": sentence.strip()})
                    break
    return leaks


_REWRITE_PROMPT = (
    "Bạn là biên tập viên khoa học. Các câu dưới đây khẳng định như một kết quả đã được chứng minh, nhưng bằng chứng chưa đủ "
    "(Research Knowledge Model). Viết lại MỖI câu thành dạng giả thuyết/kỳ vọng hoặc nêu rõ đây là hạn chế (ví dụ 'we hypothesize', "
    "'we expect', 'remains to be verified'), giữ nguyên ngôn ngữ, trích dẫn [n], tên riêng, số liệu và ý nghĩa kỹ thuật; không thêm số liệu mới.\n"
    'Chỉ trả JSON: {"rewrites": [{"original": "<câu gốc nguyên văn>", "rewritten": "<câu mới>"}]}'
)


def soften_leaked_claims(
    report: str, leaks: list[dict[str, str]], gateway: LLMGateway, model_name: str | None
) -> tuple[str, list[dict[str, str]]]:
    """Viết lại các câu rò rỉ bằng 1 lời gọi LLM. Trả (báo cáo mới, các câu không sửa được)."""
    if not leaks:
        return report, []
    listing = "\n".join(f"- ({lk['claim_id']}) {lk['sentence']}" for lk in leaks)
    try:
        response = gateway.generate(
            messages=[Message(role="system", content=_REWRITE_PROMPT), Message(role="user", content=listing)],
            model_name=model_name,
        )
        parsed = parse_llm_json(response.text)
    except LLMGatewayError:
        logger.warning("Không hạ giọng được các câu claim chưa chứng minh", exc_info=True)
        return report, leaks
    rewrites = parsed.get("rewrites", []) if isinstance(parsed, dict) else []
    new_text = {r["original"]: r["rewritten"].strip() for r in rewrites
                if isinstance(r, dict) and isinstance(r.get("original"), str) and isinstance(r.get("rewritten"), str) and r["rewritten"].strip()}
    unresolved: list[dict[str, str]] = []
    for lk in leaks:
        rewritten = new_text.get(lk["sentence"])
        still_assertive = bool(rewritten) and bool(_ASSERTIVE.search(rewritten)) and not _HEDGE.search(rewritten)
        if rewritten and not still_assertive and lk["sentence"] in report:
            report = report.replace(lk["sentence"], rewritten, 1)
        else:
            unresolved.append(lk)
    return report, unresolved
