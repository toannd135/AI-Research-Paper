"""Scientific Consistency QA — kiểm tra luật (không LLM) bắt các lớp lỗi khoa học, không chỉ từng lỗi cụ thể đã gặp.

- claim–evidence: câu khẳng định "không có/không nguồn nào" về một loại bằng chứng trong khi record/câu nguyên văn cho thấy có.
- thuật ngữ: một khái niệm viết nhiều cách (T1c/T1ce/T1Gd, HD95/95% Hausdorff, tumor/tumour…).
- phạm vi: Abstract/tiêu đề nêu mốc năm muộn hơn nguồn mới nhất trong References.
- overclaim: Abstract/Conclusion dùng "significant", "outperform", "state-of-the-art"… khi không có kiểm định/không cùng giao thức.
- taxonomy: một nguồn [n] nằm ở nhiều nhóm của CÙNG một trục mà không giải thích.
- NR: bảng có ô NR nhưng không định nghĩa NR (NR ≠ "không thực hiện").
Tất cả là cảnh báo (WARNING) để người viết sửa; không sửa văn bản.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.evidence import study_profile as sp
from app.agent.evidence.quant_check import ResultRecord

_FENCE_RE = re.compile(r"```(\w+)[ \t]*\n(.*?)```", re.DOTALL)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|\n+")
_HEAD_RE = re.compile(r"^#{1,3}\s+(.*)$", re.MULTILINE)
MAX_ITEMS = 6
ABSENCE_WINDOW = 70  # số ký tự sau từ phủ định để tìm chủ đề bị phủ nhận

# ---------- claim–evidence ----------
_ABSENCE_RE = re.compile(
    r"\b(?:no|none of|not any|neither|lacks?|lacking|absence of|never|without any)\b|\bdo(?:es)? not (?:report|provide|evaluate|include|assess)",
    re.I,
)
# phát biểu về ma trận đầy đủ/so sánh liên nghiên cứu vẫn đúng khi chỉ có bằng chứng một phần
_QUALIFIED_RE = re.compile(
    r"\b(?:complete|all \d+|all possible|every|cross-study|standardi[sz]ed|comparable|matrix|across (?:all|editions|studies|sources)|pooled|meta-analy\w+)\b",
    re.I,
)
_TOPICS: dict[str, re.Pattern[str]] = {
    "missing-modality results": re.compile(r"missing[- ]modalit\w* (?:results?|performance|experiments?|evaluations?|ablations?|settings?|scenarios?)|modality subsets?|per-subset|absent (?:modalit|sequence)|incomplete modalit|per-modality|single-modality", re.I),
    "variance (SD/CI)": re.compile(r"standard deviation|confidence interval|\bvariance\b|\bSD\b|error bars?", re.I),
    "computational cost": re.compile(r"latency|\bFLOPs\b|GFLOPs|number of parameters|parameter count|model size|inference time|\bFPS\b", re.I),
    "external validation": re.compile(r"external (?:validation|test)|multi-?cent(?:er|re) (?:validation|evaluation|test)", re.I),
    "uncertainty/calibration": re.compile(r"uncertaint|calibrat", re.I),
    "code availability": re.compile(r"code (?:availability|is available|release)|open-source code|publicly available code", re.I),
}
_EFF = re.compile(r"^(?:params|parameters|gflops|flops|inferencetime)$")


def _evidence_counts(records: list[ResultRecord], paper_to_n: dict[str, int], attrs: dict[str, dict[str, dict[str, Any]]]) -> dict[str, int]:
    from app.agent.evidence.quant_analysis import modality_matrix_stats

    return {
        "missing-modality results": modality_matrix_stats(records, paper_to_n)["groups"] if paper_to_n else 0,
        "variance (SD/CI)": sum(1 for r in records if r.spread is not None),
        "computational cost": sum(1 for r in records if _EFF.match(re.sub(r"[\s_-]+", "", r.metric.lower()))),
        "external validation": sp.count(attrs, "external_validation"),
        "uncertainty/calibration": sp.count(attrs, "uncertainty"),
        "code availability": sp.count(attrs, "code_available"),
    }


def _body(text: str) -> str:
    return _FENCE_RE.sub("", re.split(r"\n#{1,3}\s*References\b", text, maxsplit=1)[0])


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip() and not s.lstrip().startswith(("|", "#"))]


def check_absence_claims(text: str, records: list[ResultRecord], paper_to_n: dict[str, int], attrs: dict[str, dict[str, dict[str, Any]]]) -> list[str]:
    counts = _evidence_counts(records, paper_to_n, attrs)
    out: list[str] = []
    for sentence in _sentences(_body(text)):
        if _QUALIFIED_RE.search(sentence):
            continue
        # chủ đề phải nằm ngay sau từ phủ định (cùng mệnh đề), không chỉ cùng câu
        windows = [sentence[m.start() : m.end() + ABSENCE_WINDOW] for m in _ABSENCE_RE.finditer(sentence)]
        topic = next((t for t, rx in _TOPICS.items() if counts[t] and any(rx.search(w) for w in windows)), None)
        if topic:
            out.append(f"claim–evidence: '{sentence[:140]}' phủ nhận {topic} nhưng có {counts[topic]} bằng chứng đã trích/xác minh")
    return out[:MAX_ITEMS]


# ---------- thuật ngữ ----------
_TERM_GROUPS: tuple[tuple[str, ...], ...] = (
    (r"\bT1c\b", r"\bT1ce\b", r"\bT1Gd\b", r"\bT1-Gd\b", r"\bT1\+C\b", r"\bT1 post-contrast\b"),
    (r"\bHD95\b", r"\bHD 95\b", r"\b95% Hausdorff\b", r"\bHausdorff95\b"),
    (r"\btumor\b", r"\btumour\b"),
    (r"\bgeneralization\b", r"\bgeneralisation\b"),
    (r"\bmodeling\b", r"\bmodelling\b"),
)


def check_terminology(text: str) -> list[str]:
    body = re.split(r"\n#{1,3}\s*References\b", text, maxsplit=1)[0]
    out = []
    for group in _TERM_GROUPS:
        used = {re.sub(r"\\b|\\", "", rx): n for rx in group if (n := len(re.findall(rx, body)))}
        if len(used) >= 2:
            forms = ", ".join(f"{k} ×{v}" for k, v in sorted(used.items(), key=lambda kv: -kv[1]))
            out.append(f"thuật ngữ không nhất quán: {forms} — chọn một cách viết (định nghĩa viết tắt một lần)")
    return out


# ---------- phạm vi ----------
_YEAR_RANGE_RE = re.compile(r"\b((?:19|20)\d{2})\s*[–—-]\s*((?:19|20)\d{2})\b|\b(?:up to|through|until)\s+((?:19|20)\d{2})\b", re.I)


def _section(text: str, *names: str) -> str:
    heads = list(_HEAD_RE.finditer(text))
    for i, h in enumerate(heads):
        if any(n in h.group(1).lower() for n in names):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            return text[h.end() : end]
    return ""


def check_scope(text: str) -> list[str]:
    refs = _section(text, "references")
    ref_years = [int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", refs)]
    if not ref_years:
        return []
    latest = max(ref_years)
    front = text.split("\n", 1)[0] + "\n" + _section(text, "abstract")
    out = []
    for m in _YEAR_RANGE_RE.finditer(front):
        end = int(m.group(2) or m.group(3))
        if end > latest:
            out.append(f"phạm vi: Abstract/tiêu đề nêu '{m.group(0)}' nhưng nguồn mới nhất trong References là {latest} — thu hẹp phạm vi hoặc bổ sung nguồn")
    return out


# ---------- overclaim ----------
_SIGNIF_RE = re.compile(r"\b(?:statistically )?significant(?:ly)?\b(?! (?:clinical|challenge|attention|interest|role))", re.I)
_RANK_RE = re.compile(r"\boutperform\w*|\bsuperior\b|\bbest[- ]performing\b|\bstate[- ]of[- ]the[- ]art\b|\bprove[sdn]?\b|\bdefinitive(?:ly)?\b", re.I)
_SCOPED_RE = re.compile(r"under (?:the same|matched|identical)|on the same|within (?:the same|a single|each)|as reported|reported by|according to|in \[\d+\]|\[\d+\] report", re.I)
_NEG_RE = re.compile(r"\b(?:no|not|cannot|without|neither)\b", re.I)


def check_overclaims(text: str, records: list[ResultRecord]) -> list[str]:
    has_variance = any(r.spread is not None for r in records)
    out = []
    for name in ("abstract", "conclusion"):
        for sentence in _sentences(_FENCE_RE.sub("", _section(text, name))):
            if _NEG_RE.search(sentence):
                continue
            if _SIGNIF_RE.search(sentence) and not has_variance:
                out.append(f"overclaim ({name}): '{sentence[:120]}' — không có kiểm định/sai số nào được trích, không dùng 'significant'")
            elif _RANK_RE.search(sentence) and not _SCOPED_RE.search(sentence):
                out.append(f"overclaim ({name}): '{sentence[:120]}' — xếp hạng/khẳng định mạnh không gắn với cùng giao thức đánh giá")
    return out[:MAX_ITEMS]


# ---------- bảng: taxonomy và NR ----------
def _tables(text: str) -> list[dict[str, Any]]:
    from app.agent.evidence.consistency_check import _pipe_tables

    out = []
    for m in _FENCE_RE.finditer(text):
        if m.group(1) == "table":
            try:
                spec = json.loads(m.group(2))
            except ValueError:
                continue
            if isinstance(spec, dict):
                out.append({**spec, "_after": text[m.end() : m.end() + 400]})
    for spec in _pipe_tables(text):
        out.append({**spec, "_after": ""})
    return out


def check_taxonomy_membership(text: str) -> list[str]:
    out = []
    for spec in _tables(text):
        if "taxonom" not in str(spec.get("caption", "")).lower():
            continue
        axis, where = "", {}
        for row in spec.get("rows") or []:
            if not isinstance(row, list) or not row:
                continue
            axis = str(row[0]).strip(" *") or axis
            category = str(row[1]).strip() if len(row) > 1 else ""
            for n in set(re.findall(r"\[(\d+)\]", " ".join(str(c) for c in row))):
                where.setdefault((axis, n), set()).add(category)
        for (ax, n), cats in sorted(where.items()):
            if len(cats) > 1:
                out.append(f"taxonomy: [{n}] nằm ở {len(cats)} nhóm của trục '{ax}' ({'; '.join(sorted(cats))[:100]}) — chọn nhóm chính hoặc giải thích")
    return out[:MAX_ITEMS]


_NR_DEF_RE = re.compile(r"\bNR\s*(?:=|:|means|denotes|indicates)|not reported", re.I)


def check_nr_legend(text: str) -> list[str]:
    out = []
    for spec in _tables(text):
        cells = [str(c) for row in spec.get("rows") or [] if isinstance(row, list) for c in row]
        if any(re.match(r"^NR\b", c) for c in cells) and not _NR_DEF_RE.search(str(spec.get("caption", "")) + spec.get("_after", "")):
            out.append(f"bảng '{str(spec.get('caption', ''))[:60]}' dùng NR nhưng không định nghĩa (NR = không báo cáo/không trích được, không phải 'không làm')")
    return out[:MAX_ITEMS]


def run_science_qa(
    text: str, records: list[ResultRecord], paper_to_n: dict[str, int], attrs: dict[str, dict[str, dict[str, Any]]] | None = None
) -> list[str]:
    attrs = attrs or {}
    return (
        check_absence_claims(text, records, paper_to_n, attrs)
        + check_terminology(text)
        + check_scope(text)
        + check_overclaims(text, records)
        + check_taxonomy_membership(text)
        + check_nr_legend(text)
    )
