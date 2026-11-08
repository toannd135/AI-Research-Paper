"""Chuẩn hóa cấu trúc paper sau khi ghép các chặng: đánh số lại mục/bảng/hình, dọn trích dẫn treo.

Các chặng sinh độc lập nên dễ lệch số (mục 1.4 nằm sau 2.1, nhiều 'Figure 1'). Hàm ở đây chạy trên markdown
đã ghép, không gọi LLM.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_H2_NUM_RE = re.compile(r"^(##\s+)(\d+)\.(\s+.*)$")
_H3_NUM_RE = re.compile(r"^(###\s+)(\d+)\.(\d+)(\s+.*)$")
_CAPTION_RE = re.compile(r"^(\*\*)(Table|Figure)\s+(\d+)([:.]\s*)", re.MULTILINE)
_CITE_RE = re.compile(r"\[(\d+)\]")


def _split_fences(text: str) -> list[tuple[bool, str]]:
    """Tách văn bản thành các đoạn (is_code, nội dung) để không sửa bên trong khối ```."""
    parts: list[tuple[bool, str]] = []
    pos = 0
    for m in _FENCE_RE.finditer(text):
        if m.start() > pos:
            parts.append((False, text[pos : m.start()]))
        parts.append((True, m.group(0)))
        pos = m.end()
    if pos < len(text):
        parts.append((False, text[pos:]))
    return parts


def renumber_sections(text: str) -> str:
    """Đánh số lại '## N.' và '### N.M' theo thứ tự xuất hiện; mục con đi theo mục cha liền trước."""
    top = 0
    sub = 0
    out: list[str] = []
    for is_code, chunk in _split_fences(text):
        if is_code:
            out.append(chunk)
            continue
        lines = chunk.split("\n")
        for i, line in enumerate(lines):
            m2 = _H2_NUM_RE.match(line)
            if m2:
                top += 1
                sub = 0
                lines[i] = f"{m2.group(1)}{top}.{m2.group(3)}"
                continue
            m3 = _H3_NUM_RE.match(line)
            if m3 and top:
                sub += 1
                lines[i] = f"{m3.group(1)}{top}.{sub}{m3.group(4)}"
        out.append("\n".join(lines))
    return "".join(out)


_REF_RE = re.compile(r"\b(Table|Figure)\s+(\d+)\b")
_WORD_RE = re.compile(r"[a-z0-9]{4,}")
_STOP = frozenset(
    {"table", "figure", "with", "that", "this", "from", "which", "their", "these", "those", "between", "across", "within", "each", "into", "than", "over", "under", "when", "where", "while", "using", "based"}
)


def _tokens(s: str) -> set[str]:
    return {w for w in _WORD_RE.findall(s.lower()) if w not in _STOP}


def renumber_captions_report(text: str) -> tuple[str, list[str]]:
    """Đánh số lại '**Table N:' / '**Figure N:' tuần tự và cập nhật tham chiếu trong thân bài.

    Số cũ chỉ xuất hiện ở 1 chú thích thì mọi 'Table N' được đổi theo. Số cũ trùng nhiều chú thích (do các chặng sinh độc lập,
    ví dụ hai 'Table 4') thì chọn chú thích hợp nhất theo mức trùng từ giữa câu chứa tham chiếu và chú thích, hòa thì lấy chú thích
    gần nhất trong văn bản. Trả về (văn bản mới, danh sách tham chiếu gán chỉ dựa vào vị trí — độ tin cậy thấp).
    """
    captions: list[dict] = []
    counters = {"Table": 0, "Figure": 0}
    for m in _CAPTION_RE.finditer(text):
        kind = m.group(2)
        counters[kind] += 1
        line_end = text.find("\n", m.start())
        captions.append(
            {"kind": kind, "old": int(m.group(3)), "new": counters[kind], "pos": m.start(), "tokens": _tokens(text[m.start() : line_end if line_end != -1 else len(text)])}
        )
    by_old: dict[tuple[str, int], list[dict]] = {}
    for c in captions:
        by_old.setdefault((c["kind"], c["old"]), []).append(c)

    new_numbers = iter(captions)

    def _cap(m: re.Match) -> str:
        c = next(new_numbers)
        return f"{m.group(1)}{c['kind']} {c['new']}{m.group(4)}"

    low_confidence: list[str] = []
    out_lines: list[str] = []
    offset = 0
    for line in text.split("\n"):
        if line.startswith(("**Table ", "**Figure ")):
            out_lines.append(line)
        else:
            sentence_tokens = _tokens(line)

            def _ref(m: re.Match, base: int = offset, tokens: set[str] = sentence_tokens) -> str:
                kind, old = m.group(1), int(m.group(2))
                candidates = by_old.get((kind, old), [])
                if not candidates:
                    return m.group(0)
                if len(candidates) == 1:
                    return f"{kind} {candidates[0]['new']}"
                here = base + m.start()
                best = max(candidates, key=lambda c: (len(tokens & c["tokens"]), -abs(c["pos"] - here)))
                if not tokens & best["tokens"]:
                    low_confidence.append(f"{kind} {old} -> {kind} {best['new']}")
                return f"{kind} {best['new']}"

            out_lines.append(_REF_RE.sub(_ref, line))
        offset += len(line) + 1
    return _CAPTION_RE.sub(_cap, "\n".join(out_lines)), low_confidence


def renumber_captions(text: str) -> str:
    return renumber_captions_report(text)[0]


def strip_dangling_citations(text: str, n_refs: int) -> tuple[str, list[int]]:
    """Xóa marker [n] không có mục tương ứng trong References (n < 1 hoặc n > n_refs).

    Trả về (văn bản đã dọn, danh sách số bị xóa). n_refs = 0 xóa mọi marker.
    Khối code/mermaid/chart được giữ nguyên (ví dụ chỉ số mảng).
    """
    removed: list[int] = []

    def _drop(m: re.Match) -> str:
        n = int(m.group(1))
        if 1 <= n <= n_refs:
            return m.group(0)
        removed.append(n)
        return ""

    out: list[str] = []
    for is_code, chunk in _split_fences(text):
        if is_code:
            out.append(chunk)
            continue
        cleaned = _CITE_RE.sub(_drop, chunk)
        cleaned = re.sub(r"[ \t]+([,.;:])", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        out.append(cleaned)
    return "".join(out), removed


def source_diversity_warning(text: str, n_refs: int) -> str | None:
    """Cảnh báo khi hầu hết trích dẫn dồn vào một nguồn (dấu hiệu gán nguồn hàng loạt)."""
    counts = Counter(int(n) for n in _CITE_RE.findall(_FENCE_RE.sub("", text)))
    total = sum(counts.values())
    if n_refs == 0:
        return "Không có nguồn nào được trích dẫn (References rỗng)"
    if total >= 10 and counts:
        top, top_n = counts.most_common(1)[0]
        if top_n / total > 0.8 and n_refs <= 2:
            return f"{top_n}/{total} trích dẫn dồn vào [{top}], chỉ có {n_refs} nguồn"
    return None


# 'Table 2 of [7]' là bảng trong paper nguồn, không phải bảng của bài này.
_SOURCE_REF_RE = re.compile(r"\b(Table|Figure)\s+(\d+)(?=\s+(?:of|in|from)\s+(?:\[\d+\]|the original))")


def check_cross_references(text: str) -> list[str]:
    """Lỗi chặn: tham chiếu 'Table N'/'Figure N' trong thân bài vượt quá số chú thích thực có (tham chiếu treo)."""
    counts = Counter(m.group(2) for m in _CAPTION_RE.finditer(text))
    body_lines = [ln for ln in _FENCE_RE.sub("", text).split("\n") if not ln.startswith(("**Table ", "**Figure "))]
    body = _SOURCE_REF_RE.sub("", "\n".join(body_lines))
    problems: list[str] = []
    for kind in ("Table", "Figure"):
        total = counts.get(kind, 0)
        dangling = sorted({int(n) for k, n in _REF_RE.findall(body) if k == kind and int(n) > total})
        if dangling:
            problems.append(f"{kind} {dangling} được nhắc trong thân bài nhưng bài chỉ có {total} {kind.lower()} có chú thích")
    return problems


def finalize_structure_report(text: str) -> tuple[str, list[str], list[str]]:
    """Đánh số lại mục, bảng, hình sau khi ghép. Trả về (văn bản, lỗi tham chiếu treo, tham chiếu gán theo vị trí)."""
    fixed, low_confidence = renumber_captions_report(renumber_sections(text))
    return fixed, check_cross_references(fixed), low_confidence


def finalize_structure(text: str) -> str:
    """Đánh số lại mục, bảng, hình sau khi ghép."""
    return finalize_structure_report(text)[0]
