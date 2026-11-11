"""Chuẩn hóa cấu trúc paper sau khi ghép các chặng: đánh số lại mục/bảng/hình, dọn trích dẫn treo.

Các chặng sinh độc lập nên dễ lệch số (mục 1.4 nằm sau 2.1, nhiều 'Figure 1'). Hàm ở đây chạy trên markdown
đã ghép, không gọi LLM.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter

from app.agent.evidence.citation_validator import expand_citation_clusters

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_H2_NUM_RE = re.compile(r"^(##\s+)(\d+)\.(\s+.*)$")
_H3_NUM_RE = re.compile(r"^(###\s+)(\d+)\.(\d+)(\s+.*)$")
_CAPTION_RE = re.compile(r"^(\*\*)(Table|Figure)\s+(\d+)([:.]\s*)", re.MULTILINE)
_CITE_RE = re.compile(r"\[(\d+)\]")
_CITE_SEP_RE = re.compile(r"(,[ \t]*)?\[(\d+)\]")
# '[52, Table 1]' / '[3, 52, p. 4]': danh sách số rồi phần định vị (bảng/hình/trang/mục/phương trình + số).
# Không nhận khoảng toán học '[0, L]' / '[0, T]'.
_LOCATOR = r"(?:Table|Tab\.|Figure|Fig\.?|pp\.|p\.|Section|Sec\.?|Eq\.?)\s*\d+"
_LOCATED_CITE_RE = re.compile(rf"\[(\d+(?:\s*,\s*\d+)*)\s*,\s*({_LOCATOR}[^\[\]\n]{{0,30}})\]")


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
    seen: dict[str, set[str]] = {}  # số cũ -> các số mới (trùng số cũ khác số mới thì mơ hồ, không đổi tham chiếu)
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
                seen.setdefault(str(int(m2.group(2))), set()).add(str(top))
                lines[i] = f"{m2.group(1)}{top}.{m2.group(3)}"
                continue
            m3 = _H3_NUM_RE.match(line)
            if m3 and top:
                sub += 1
                seen.setdefault(f"{int(m3.group(2))}.{int(m3.group(3))}", set()).add(f"{top}.{sub}")
                lines[i] = f"{m3.group(1)}{top}.{sub}{m3.group(4)}"
        out.append("\n".join(lines))
    renumbered = "".join(out)
    mapping = {old: next(iter(new)) for old, new in seen.items() if len(new) == 1}
    if all(old == new for old, new in mapping.items()) and len(mapping) == len(seen):
        return renumbered
    return _update_section_refs(renumbered, mapping)


_SECTION_REF_RE = re.compile(r"\b(Section|Sec\.)(\s+)(\d+(?:\.\d+)?)\b|(§\s*)(\d+(?:\.\d+)?)\b")


def _update_section_refs(text: str, mapping: dict[str, str]) -> str:
    """Cập nhật 'Section N' / 'Section N.M' / '§N' trong thân bài theo ánh xạ số mục cũ -> mới (bỏ qua References, khối ```, heading)."""
    head, sep, refs = text.partition("\n## References")
    unknown: set[str] = set()

    def _ref(m: re.Match) -> str:
        num = m.group(3) or m.group(5)
        key = ".".join(str(int(x)) for x in num.split("."))
        new = mapping.get(key)
        if new is None:
            unknown.add(num)
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}{new}" if m.group(3) else f"{m.group(4)}{new}"

    out: list[str] = []
    for is_code, chunk in _split_fences(head):
        if is_code:
            out.append(chunk)
            continue
        out.append("\n".join(ln if ln.lstrip().startswith("#") else _SECTION_REF_RE.sub(_ref, ln) for ln in chunk.split("\n")))
    if unknown:
        logger.warning("Tham chiếu tới mục không tồn tại (hoặc số mục cũ mơ hồ) sau khi đánh số lại, giữ nguyên: %s", sorted(unknown))
    return "".join(out) + sep + refs


_REF_RE = re.compile(r"\b(Table|Figure)\s+(\d+)\b")
_WORD_RE = re.compile(r"[a-z0-9]{4,}")
_STOP = frozenset(
    {"table", "figure", "with", "that", "this", "from", "which", "their", "these", "those", "between", "across", "within", "each", "into", "than", "over", "under", "when", "where", "while", "using", "based"}
)


def _tokens(s: str) -> set[str]:
    return {w for w in _WORD_RE.findall(s.lower()) if w not in _STOP}


def renumber_captions_report(text: str, kinds: tuple[str, ...] = ("Table", "Figure")) -> tuple[str, list[str]]:
    """Đánh số lại '**Table N:' / '**Figure N:' tuần tự và cập nhật tham chiếu trong thân bài.

    Số cũ chỉ xuất hiện ở 1 chú thích thì mọi 'Table N' được đổi theo. Số cũ trùng nhiều chú thích (do các chặng sinh độc lập,
    ví dụ hai 'Table 4') thì chọn chú thích hợp nhất theo mức trùng từ giữa câu chứa tham chiếu và chú thích, hòa thì lấy chú thích
    gần nhất trong văn bản. Trả về (văn bản mới, danh sách tham chiếu gán chỉ dựa vào vị trí — độ tin cậy thấp).
    """
    captions: list[dict] = []
    counters = {"Table": 0, "Figure": 0}
    for m in _CAPTION_RE.finditer(text):
        kind = m.group(2)
        if kind not in kinds:
            continue
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
        if m.group(2) not in kinds:
            return m.group(0)
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
        n = int(m.group(2))
        if 1 <= n <= n_refs:
            return m.group(0)
        removed.append(n)
        return ""

    def _drop_located(m: re.Match) -> str:
        # '[52, Table 1]': bảng/trang của nguồn [52]; nguồn không tồn tại thì bỏ cả marker (giữ 'Table 1' sẽ trỏ nhầm bảng của bài)
        nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
        valid = [n for n in nums if 1 <= n <= n_refs]
        removed.extend(n for n in nums if not 1 <= n <= n_refs)
        if not valid:
            return ""
        return "[" + ", ".join(str(n) for n in valid) + ", " + m.group(2) + "]"

    def _clean(chunk: str) -> str:
        chunk = _LOCATED_CITE_RE.sub(_drop_located, chunk)
        # Xóa marker kèm dấu phẩy nối phía trước: '[7], [73].' -> '[7].'
        cleaned = _CITE_SEP_RE.sub(_drop, expand_citation_clusters(chunk))
        # Marker đầu cụm bị xóa để lại dấu phẩy mồ côi: 'methods , [7]' -> 'methods [7]'
        cleaned = re.sub(r"([\s(])[ \t]*,[ \t]*(?=\[\d+\])", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]+([,.;:])", r"\1", cleaned)
        return re.sub(r"[ \t]{2,}", " ", cleaned)

    def _clean_json(value):
        if isinstance(value, str):
            return _clean(value) if "[" in value else value
        if isinstance(value, list):
            return [_clean_json(v) for v in value]
        if isinstance(value, dict):
            return {k: _clean_json(v) for k, v in value.items()}
        return value

    def _clean_mermaid_cluster(m: re.Match) -> str:
        nums = [int(x) for x in re.findall(r"\d+", m.group(0))]
        valid = list(dict.fromkeys(n for n in nums if 1 <= n <= n_refs))
        removed.extend(n for n in nums if not 1 <= n <= n_refs)
        return "[" + ", ".join(map(str, valid)) + "]" if valid else ""

    out: list[str] = []
    for is_code, chunk in _split_fences(text):
        if is_code:
            if chunk.startswith("```mermaid"):
                chunk = _MERMAID_CITE_RE.sub(_clean_mermaid_cluster, chunk)
                chunk = re.sub(r"(?:<br\s*/?>)+(?=\s*[\"\]])", "", chunk)  # nhãn còn '<br/>' treo sau khi bỏ hết số
                out.append(chunk)
                continue
            out.append(_clean_data_fence(chunk, _clean_json))
            continue
        out.append(_clean(chunk))
    return "".join(out), removed


# Cụm trích dẫn trong nhãn mermaid ('Early<br/>[2,38]'): không đứng sau ký tự định danh, để không đụng cú pháp nút 'A1[2019]'
_MERMAID_CITE_RE = re.compile(r"(?<![\w\]])\[\d+(?:\s*[,;–—-]\s*\d+)*\]")


_DATA_FENCE_RE = re.compile(r"^(```(?:chart|table)[ \t]*\n)(.*?)(\n?```)$", re.DOTALL)


def _clean_data_fence(block: str, fix) -> str:
    """Khối ```chart/```table: sửa chuỗi trong JSON (caption, ô bảng) bằng `fix`; JSON hỏng hoặc khối khác giữ nguyên."""
    m = _DATA_FENCE_RE.match(block)
    if not m:
        return block
    try:
        spec = json.loads(m.group(2))
    except ValueError:
        return block
    new = fix(spec)
    if new == spec:
        return block
    return m.group(1) + json.dumps(new, ensure_ascii=False) + m.group(3)


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
    counts["Figure"] = max(counts.get("Figure", 0), _count_figure_blocks(text))  # khối hình tự chèn không có chú thích vẫn được đánh số
    body_lines = [ln for ln in _FENCE_RE.sub("", text).split("\n") if not ln.startswith(("**Table ", "**Figure "))]
    body = _SOURCE_REF_RE.sub("", "\n".join(body_lines))
    problems: list[str] = []
    for kind in ("Table", "Figure"):
        total = counts.get(kind, 0)
        dangling = sorted({int(n) for k, n in _REF_RE.findall(body) if k == kind and int(n) > total})
        if dangling:
            problems.append(f"{kind} {dangling} được nhắc trong thân bài nhưng bài chỉ có {total} {kind.lower()} có chú thích")
    return problems


_FIG_FENCE_OPEN_RE = re.compile(r"^```(?:chart|image|mermaid)\b")
_FIG_CAPTION_LINE_RE = re.compile(r"^\*\*(Figure|Fig\.)\s*(\d+)(\s*[:.])")
_FIG_REF_RE = re.compile(r"\b(Figure|Fig\.)\s+(\d+)\b(?!\s+(?:of|in|from)\s+(?:\[\d+\]|the original))")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(*])")


def align_figure_captions(text: str) -> tuple[str, list[int]]:
    """Đánh số '**Figure N:' theo THỨ TỰ KHỐI HÌNH thật (chart/image/mermaid) như renderer, kể cả khối chèn tự động không có chú thích.

    Chú thích không đứng ngay trên một khối hình (khối đã bị validator bỏ) là hình ma: xóa chú thích và mọi câu nhắc tới số đó
    (tránh hai 'Figure 7' và câu mô tả hình không tồn tại). Trả về (văn bản, các số hình ma cũ).
    """
    lines = text.split("\n")
    mapping: dict[int, int] = {}
    orphans: list[int] = []
    drop: set[int] = set()
    ordinal = 0
    in_fence = False
    for i, line in enumerate(lines):
        if line.startswith("```"):
            if not in_fence and _FIG_FENCE_OPEN_RE.match(line):
                ordinal += 1
            in_fence = not in_fence
            continue
        m = None if in_fence else _FIG_CAPTION_LINE_RE.match(line)
        if not m:
            continue
        nxt = next((ln for ln in lines[i + 1 :] if ln.strip()), "")
        old = int(m.group(2))
        if _FIG_FENCE_OPEN_RE.match(nxt):
            new = ordinal + 1
            mapping.setdefault(old, new)
            lines[i] = f"**{m.group(1)} {new}{m.group(3)}" + line[m.end() :]
        else:
            orphans.append(old)
            drop.add(i)
    if not mapping and not orphans:
        return text, []
    ghost = {n for n in orphans if n not in mapping}

    def _ref(m: re.Match) -> str:
        old = int(m.group(2))
        return f"{m.group(1)} {mapping[old]}" if old in mapping else m.group(0)

    out: list[str] = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if i in drop:
            continue
        if in_fence or _FIG_CAPTION_LINE_RE.match(line):
            out.append(line)
            continue
        if ghost:
            parts = _SENTENCE_RE.split(line)
            kept = [p for p in parts if not any(int(r.group(2)) in ghost for r in _FIG_REF_RE.finditer(p))]
            if len(kept) != len(parts):
                logger.warning("Bỏ %d câu nhắc tới hình không còn khối hình: %s", len(parts) - len(kept), sorted(ghost))
                line = " ".join(kept)
        out.append(_FIG_REF_RE.sub(_ref, line))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)), orphans


def _count_figure_blocks(text: str) -> int:
    return sum(1 for ln in text.split("\n") if _FIG_FENCE_OPEN_RE.match(ln))


_H2_TITLE_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$", re.M)
_ORG_HEADING_RE = re.compile(r"^###\s+\d+\.\d+\s+(?:Paper Organi[sz]ation|Organi[sz]ation of (?:the|this) (?:Paper|Survey|Article)|Paper Structure|Outline)\s*$", re.I | re.M)
_NON_BODY = re.compile(r"^(?:References|Bibliography|Appendix|Acknowledg)", re.I)


def _body_sections(text: str) -> list[tuple[int, str]]:
    return [(int(m.group(1)), m.group(2).strip()) for m in _H2_TITLE_RE.finditer(text) if not _NON_BODY.match(m.group(2).strip())]


def rebuild_paper_organization(text: str) -> tuple[str, bool]:
    """Đoạn 'Paper Organization' do LLM viết theo dàn ý cũ thường lệch số mục → viết lại tất định từ heading '## N.' thật."""
    m = _ORG_HEADING_RE.search(text)
    sections = [(n, t) for n, t in _body_sections(text) if n > 1]
    if not m or len(sections) < 2:
        return text, False
    nxt = re.compile(r"^#{2,3}\s", re.M).search(text, m.end())
    end = nxt.start() if nxt else len(text)
    parts = [f"Section {n} presents {t}" for n, t in sections[:-1]]
    last_n, last_t = sections[-1]
    tail = f"Section {last_n} concludes the paper" if re.match(r"conclu", last_t, re.I) else f"Section {last_n} presents {last_t}"
    para = "The remainder of this paper is organized as follows. " + "; ".join(parts) + "; and " + tail + "."
    new = text[: m.end()] + "\n\n" + para + "\n\n" + text[end:].lstrip("\n")
    return new, new != text


# '(Section 5 of the full manuscript)', '(§1.3, §5.4 of the Draft Basis)': tham chiếu tới bản nháp nội bộ, không phải bài này
_DRAFT_PAREN_RE = re.compile(
    r"(?P<pre>\b(?P<name>[A-Z][A-Za-z&\- ]{2,40}?)\s*)?\(\s*(?:see\s+)?(?P<refs>(?:(?:Section|Sec\.|§)\s*\d+(?:\.\d+)?[,;\s]*(?:and\s+)?)+)"
    r"(?:of|in)\s+the\s+(?:full\s+manuscript|draft\s+basis|draft|original\s+draft|full\s+paper)\s*\)",
    re.I,
)
_DRAFT_INLINE_RE = re.compile(r"\s+(?:of|in)\s+the\s+(?:full\s+manuscript|draft\s+basis)\b", re.I)
# 'Table 1 of the Draft Basis' là bảng của nguồn mà bản nháp đã dẫn, không phải bảng của bài → không được để lại 'Table 1'
_DRAFT_TABLE_RE = re.compile(r"\b(Table|Figure|Fig\.)\s+\d+\s+(?:of|in)\s+the\s+(?:full\s+manuscript|draft\s+basis)\b", re.I)
# câu mô tả cách vẽ hình ('rendered left-to-right (graph LR)', 'mermaid') là chi tiết công cụ, không thuộc nội dung bài
_RENDER_META_RE = re.compile(r"\((?:graph|flowchart)\s+(?:LR|RL|TD|TB)\)|\b(?:graph|flowchart)\s+(?:LR|TD)\b|\bmermaid\b", re.I)


def fix_internal_draft_refs(text: str) -> tuple[str, list[str]]:
    """Bỏ tham chiếu tới 'full manuscript'/'Draft Basis'; nếu ngay trước có tên mục khớp đúng một heading '## N.' thì trỏ về mục đó."""
    sections = _body_sections(text)
    changes: list[str] = []

    def _paren(m: re.Match) -> str:
        name = (m.group("name") or "").strip()
        words = _tokens(name) - _GENERIC
        hits = [n for n, t in sections if words and words & _tokens(t)] if words else []
        changes.append(m.group(0).strip()[:80])
        pre = m.group("pre") or ""
        if len(hits) == 1:
            return f"{pre}(Section {hits[0]})"
        return pre.rstrip()

    out: list[str] = []
    for is_code, chunk in _split_fences(text):
        if is_code:
            out.append(chunk)
            continue
        chunk = _DRAFT_PAREN_RE.sub(_paren, chunk)
        chunk, n_tab = _DRAFT_TABLE_RE.subn(
            lambda m: "The corresponding source " + ("table" if m.group(1).lower().startswith("tab") else "figure"), chunk
        )
        chunk = re.sub(r"(?<=[a-z,;(] )The corresponding source", "the corresponding source", chunk)
        if n_tab:
            changes.append(f"{n_tab} source table/figure")
        lines = []
        for ln in chunk.split("\n"):
            # chỉ bỏ qua heading/bảng/dòng caption '**Figure N:'; câu mở đầu bằng '**Figure 2** presents…' vẫn được lọc
            if not ln.lstrip().startswith(("#", "|")) and not _CAPTION_LINE_RE.match(ln.lstrip()) and _RENDER_META_RE.search(ln):
                parts = _SENTENCE_RE.split(ln)
                kept = [p for p in parts if not _RENDER_META_RE.search(p)]
                changes.append(f"{len(parts) - len(kept)} render-meta sentence")
                ln = " ".join(kept)
            lines.append(ln)
        chunk = "\n".join(lines)
        chunk, n = _DRAFT_INLINE_RE.subn("", chunk)
        if n:
            changes.append(f"{n} inline")
        out.append(re.sub(r"[ \t]+([,.;:)])", r"\1", chunk) if changes else chunk)
    return "".join(out), changes


def finalize_structure_report(text: str) -> tuple[str, list[str], list[str]]:
    """Đánh số lại mục, bảng, hình sau khi ghép. Trả về (văn bản, lỗi tham chiếu treo, tham chiếu gán theo vị trí).

    Có khối hình → số hình theo thứ tự khối (khớp renderer), bỏ chú thích hình ma; không có → đánh số theo chú thích như cũ.
    """
    text = renumber_sections(text)
    text, rebuilt = rebuild_paper_organization(text)
    if rebuilt:
        logger.warning("Viết lại đoạn 'Paper Organization' theo heading thật")
    text, draft_refs = fix_internal_draft_refs(text)
    if draft_refs:
        logger.warning("Bỏ/sửa tham chiếu tới bản nháp nội bộ: %s", draft_refs)
    if _count_figure_blocks(text):
        text, orphans = align_figure_captions(text)
        if orphans:
            logger.warning("Bỏ chú thích của hình không còn khối hình (bị validator loại): Figure %s", orphans)
        fixed, low_confidence = renumber_captions_report(text, kinds=("Table",))
    else:
        fixed, low_confidence = renumber_captions_report(text)
    fixed, rematched = rematch_refs_by_caption(fixed)
    if rematched:
        logger.warning("Đổi tham chiếu bảng/hình theo nội dung chú thích: %s", rematched)
    return fixed, check_cross_references(fixed), low_confidence


def _final_captions(text: str) -> dict[tuple[str, int], set[str]]:
    """Từ khoá chú thích theo số cuối: Table theo '**Table N:'; Figure theo thứ tự khối hình (nhãn phía trên hoặc caption JSON)."""
    caps: dict[tuple[str, int], set[str]] = {}
    for m in _CAPTION_RE.finditer(text):
        if m.group(2) == "Table":
            end = text.find("\n", m.start())
            caps[("Table", int(m.group(3)))] = _tokens(text[m.start() : end if end != -1 else len(text)])
    lines = text.split("\n")
    ordinal = 0
    in_fence = False
    for i, line in enumerate(lines):
        if not line.startswith("```"):
            continue
        if not in_fence and _FIG_FENCE_OPEN_RE.match(line):
            ordinal += 1
            words: set[str] = set()
            prev = next((ln for ln in reversed(lines[:i]) if ln.strip()), "")
            if _FIG_CAPTION_LINE_RE.match(prev):
                words |= _tokens(prev)
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("```")), len(lines))
            try:
                spec = json.loads("\n".join(lines[i + 1 : end]))
            except ValueError:
                spec = None
            if isinstance(spec, dict):
                words |= _tokens(str(spec.get("caption", "")))
            caps[("Figure", ordinal)] = words
        in_fence = not in_fence
    return caps


_CAPTION_WINDOW = 40
# từ chung chung xuất hiện ở hầu hết chú thích/câu dẫn, không dùng để khớp lại số
_GENERIC = frozenset(
    {"results", "performance", "comparison", "summary", "overview", "methods", "method", "studies", "study", "dataset", "datasets",
     "shown", "shows", "show", "presents", "present", "presented", "reported", "values", "approaches", "models", "model", "metrics",
     "summarizes", "summarises", "illustrates", "provides", "lists", "details", "brats", "dice", "selected", "representative"}
)


# 'Table 1 of [3]' / 'Table 1 in the original study' / 'Table 1 of the Draft Basis': bảng của tài liệu khác
_OTHER_SOURCE_RE = re.compile(r"\s+(?:of|in|from)\s+(?:\[\d+\]|the\s+original\b|the\s+[A-Z]|[A-Z])")
_CAPTION_LINE_RE = re.compile(r"^\*\*(?:Table|Figure|Fig\.)\s*\d+\s*[:.]")


def rematch_refs_by_caption(text: str) -> tuple[str, list[str]]:
    """'taxonomy (Table 1)' khi Table 1 không nói gì về taxonomy mà đúng MỘT bảng khác có 'taxonomy' trong chú thích → đổi số.

    Chỉ xét cụm quanh tham chiếu (cùng câu, ±40 ký tự, bỏ từ chung chung); chú thích đích phải có từ khoá và không trùng từ nào với cụm.
    """
    caps = _final_captions(text)
    if len(caps) < 2:
        return text, []
    changes: list[str] = []

    def _fix_line(line: str) -> str:
        brackets = [b.span() for b in re.finditer(r"\[[^\[\]\n]*\]", line)]

        def _ref(m: re.Match) -> str:
            kind, n = m.group(1), int(m.group(2))
            target = caps.get((kind, n))
            if not target or _OTHER_SOURCE_RE.match(line[m.end() :]):
                return m.group(0)
            if any(s < m.start() and m.end() < e for s, e in brackets):  # '[3, Table 1]': bảng của nguồn [3]
                return m.group(0)
            pre = line[max(0, m.start() - _CAPTION_WINDOW) : m.start()]
            post = line[m.end() : m.end() + _CAPTION_WINDOW]
            pre = re.split(r"[.!?]\s", pre)[-1]
            post = re.split(r"[.!?](?:\s|$)", post)[0]
            sent_pre = re.split(r"[.!?]\s", line[: m.start()])[-1]
            sent_post = re.split(r"[.!?](?:\s|$)", line[m.end() :])[0]
            if _REF_RE.search(sent_pre) or _REF_RE.search(sent_post):  # câu nhắc nhiều bảng/hình: không biết cụm từ thuộc tham chiếu nào
                return m.group(0)
            window = _tokens(f"{pre} {post}") - _GENERIC
            if not window or window & target:
                return m.group(0)
            others = [k for (kd, k), words in caps.items() if kd == kind and k != n and words & window]
            if len(others) != 1:
                return m.group(0)
            changes.append(f"{kind} {n} -> {kind} {others[0]}")
            return f"{kind} {others[0]}"

        return _REF_RE.sub(_ref, line)

    out: list[str] = []
    for is_code, chunk in _split_fences(text):
        if is_code:
            out.append(chunk)
            continue
        # chỉ dòng dạng chú thích '**Table N:' / '**Figure N.' mới bỏ qua; '**Figure 1** presents ...' là câu thân bài
        out.append("\n".join(ln if _CAPTION_LINE_RE.match(ln) else _fix_line(ln) for ln in chunk.split("\n")))
    return "".join(out), changes


def finalize_structure(text: str) -> str:
    """Đánh số lại mục, bảng, hình sau khi ghép."""
    return finalize_structure_report(text)[0]
