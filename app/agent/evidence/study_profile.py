"""Thuộc tính chất lượng/tái lập của từng nghiên cứu, lấy từ CÂU NGUYÊN VĂN trong đoạn PDF đã truy xuất (không LLM).

Mỗi thuộc tính chỉ là "Yes"/"No" khi có một câu của chính paper đó khớp mẫu (kèm trang + câu trích để người dùng đối chiếu);
không thấy thì là NR = không tìm thấy trong các đoạn đã truy xuất — KHÔNG có nghĩa là nghiên cứu không làm.
Câu nói về công trình khác (có "et al." hoặc trích dẫn [n]/(Tác giả, năm)) bị bỏ để tránh gán nhầm.
Đây là dữ kiện hỗ trợ đánh giá, không phải điểm risk-of-bias.
"""

from __future__ import annotations

import re
from typing import Any

NR = "NR"
YES = "Yes"
NO = "No"

ATTRIBUTES: dict[str, re.Pattern[str]] = {
    "external_validation": re.compile(
        r"external(?:ly)?[- ](?:validat\w*|test\w*|cohort|dataset)|independent (?:external )?(?:test|validation) (?:set|cohort|data)"
        r"|(?:multi|cross)[- ]?(?:center|centre|site|institution(?:al)?|vendor|scanner) (?:test\w*|validation|evaluation|generali[sz]ation)",
        re.I,
    ),
    "cross_validation": re.compile(r"\b(?:\d+|three|four|five|ten|k)[- ]fold\b|cross[- ]validat\w*", re.I),
    "patient_wise_split": re.compile(
        r"(?:patient|subject|case)[- ](?:wise|level|based) (?:split|partition|division|separation|cross[- ]validation)"
        r"|split\w* (?:by|at the level of|on a per-) ?(?:patient|subject)s?",
        re.I,
    ),
    "missing_random": re.compile(
        r"random(?:ly)? (?:drop|mask|remov|omit|discard)\w*(?: \w+){0,3} modalit\w*|modalit\w*(?: \w+){0,3} (?:are|is|were|was) random(?:ly)? "
        r"(?:drop|mask|remov|omit|discard)\w*|modality[- ]dropout|random modality",
        re.I,
    ),
    "missing_all_subsets": re.compile(
        r"all (?:15|fifteen|possible) (?:modality )?(?:combinations|subsets)|every (?:possible )?(?:combination|subset) of (?:the )?(?:input |available )?modalit",
        re.I,
    ),
    # chế độ deepfake: kiểm tra tổng quát hoá và độ bền
    "cross_dataset_eval": re.compile(
        r"cross[- ](?:dataset|domain|database|corpus) (?:evaluation|test\w*|setting|experiment\w*|generali[sz]ation|performance)"
        r"|(?:trained|train) on [\w+-]+(?: \w+){0,4} (?:and )?test(?:ed)? on",
        re.I,
    ),
    "unseen_generator": re.compile(
        r"unseen (?:generators?|manipulations?|forgery (?:types|methods)|attacks?|gan\w*|diffusion models?)"
        r"|cross[- ](?:generator|manipulation|forgery|method) (?:evaluation|test\w*|setting|generali[sz]ation)",
        re.I,
    ),
    "compression_robustness": re.compile(
        r"\bc23\b|\bc40\b|(?:robust\w*|resilien\w*) (?:to|against) (?:\w+ ){0,3}(?:compression|perturbation\w*|blur|noise|resiz\w*)"
        r"|(?:compression|perturbation)[- ]robust\w*|adversarial (?:attack|perturbation)s?",
        re.I,
    ),
    "uncertainty": re.compile(
        r"uncertaint\w*|calibrat\w*|expected calibration error|\bECE\b|monte[- ]carlo dropout|out[- ]of[- ]distribution|\bOOD\b|failure detection",
        re.I,
    ),
    "code_available": re.compile(
        r"github\.com|gitlab\.com|(?:source )?code (?:is|are|will be|has been|was) (?:made )?(?:publicly |freely |openly )?(?:available|released)"
        r"|publicly available at https?://",
        re.I,
    ),
}
_OTHER_WORK_RE = re.compile(r"\bet al\b|\[\d+(?:[,–-]\s*\d+)*\]|\([A-Z][A-Za-z-]+(?: et al\.?)?,? \d{4}\)")
_NEGATION_RE = re.compile(r"\b(?:not|no|without|lack(?:s|ing)?|neither|nor|unavailable)\b", re.I)
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
MAX_QUOTE = 220


def _chunks(evidence: list[Any]) -> list[tuple[str, int | None, str]]:
    out = []
    for sc in evidence or []:
        c = getattr(sc, "chunk", sc)
        pid = str(getattr(c, "paper_id", "") or (c.get("paper_id", "") if isinstance(c, dict) else ""))
        text = getattr(c, "text", None) or (c.get("text", "") if isinstance(c, dict) else "")
        page = getattr(c, "page", None) if not isinstance(c, dict) else c.get("page")
        if pid and text:
            out.append((pid, page, str(text)))
    return out


def study_attributes(evidence: list[Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """{paper_id: {thuộc tính: {"value": Yes|No, "page", "quote"}}}; chỉ có khóa khi tìm thấy câu nguyên văn."""
    found: dict[str, dict[str, dict[str, Any]]] = {}
    for pid, page, text in _chunks(evidence):
        for sentence in _SENT_RE.split(re.sub(r"\s+", " ", text)):
            if _OTHER_WORK_RE.search(sentence):
                continue
            for name, rx in ATTRIBUTES.items():
                m = rx.search(sentence)
                if not m or name in found.get(pid, {}):
                    continue
                # phủ định đứng ngay trước cụm khớp ('no external validation', 'code is not available')
                window = sentence[max(0, m.start() - 40) : m.end() + 20]
                value = NO if _NEGATION_RE.search(window) else YES
                found.setdefault(pid, {})[name] = {"value": value, "page": page, "quote": sentence.strip()[:MAX_QUOTE]}
    return found


def cell(attrs: dict[str, dict[str, Any]] | None, name: str) -> str:
    """'Yes (p. 5)' / 'No (p. 5)' / NR."""
    hit = (attrs or {}).get(name)
    if not hit:
        return NR
    return f"{hit['value']} (p. {hit['page']})" if hit.get("page") is not None else hit["value"]


def count(attrs_by_paper: dict[str, dict[str, dict[str, Any]]], name: str, value: str = YES) -> int:
    return sum(1 for a in attrs_by_paper.values() if (a.get(name) or {}).get("value") == value)
