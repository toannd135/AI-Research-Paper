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


def renumber_captions(text: str) -> str:
    """Đánh số lại '**Table N:' / '**Figure N:' tuần tự và cập nhật tham chiếu trong văn bản khi không mơ hồ.

    Số cũ xuất hiện ở đúng 1 chú thích thì mọi 'Table N' trong thân được đổi theo; số cũ trùng nhiều chú thích
    (ví dụ hai 'Figure 1') thì giữ nguyên tham chiếu vì không biết trỏ đến cái nào.
    """
    counters = {"Table": 0, "Figure": 0}
    old_counts: dict[tuple[str, int], int] = Counter()
    for m in _CAPTION_RE.finditer(text):
        old_counts[(m.group(2), int(m.group(3)))] += 1

    remap: dict[tuple[str, int], int] = {}

    def _cap(m: re.Match) -> str:
        kind, old = m.group(2), int(m.group(3))
        counters[kind] += 1
        if old_counts[(kind, old)] == 1:
            remap[(kind, old)] = counters[kind]
        return f"{m.group(1)}{kind} {counters[kind]}{m.group(4)}"

    text = _CAPTION_RE.sub(_cap, text)

    def _ref(m: re.Match) -> str:
        kind, old = m.group(1), int(m.group(2))
        new = remap.get((kind, old))
        return f"{kind} {new}" if new is not None else m.group(0)

    # Chỉ đổi tham chiếu nằm ngoài dòng chú thích vừa đánh số (chú thích bắt đầu bằng '**').
    out_lines = []
    for line in text.split("\n"):
        if line.startswith("**Table ") or line.startswith("**Figure "):
            out_lines.append(line)
        else:
            out_lines.append(re.sub(r"\b(Table|Figure)\s+(\d+)\b", _ref, line))
    return "\n".join(out_lines)


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


def finalize_structure(text: str) -> str:
    """Đánh số lại mục, bảng, hình sau khi ghép."""
    return renumber_captions(renumber_sections(text))
