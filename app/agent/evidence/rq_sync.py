"""Một nguồn duy nhất cho Research Questions (RQ): lấy từ blueprint, ép nguyên văn vào mọi mục định nghĩa RQ.

Các chặng sinh độc lập nên Introduction và Review Methodology hay tự đặt RQ khác nhau. Module này không gọi LLM:
`canonical_rqs` đọc RQ chuẩn, `enforce_rqs` ghi đè nội dung các dòng RQ trong mục "Research Questions" khi số dòng khớp,
`check_rq_definitions` báo lỗi khi hai mục định nghĩa RQ lệch nhau (lỗi chặn trong Quality Gate).
RQ chỉ được liệt kê MỘT lần (mục đầu tiên, thường là Introduction): `dedupe_rq_definitions` thay danh sách lặp ở mục sau
bằng câu tham chiếu, `check_rq_repetition` chặn ở Quality Gate nếu còn lặp.
"""

from __future__ import annotations

import re

MIN_RQS = 2
MIN_BODY_WORDS = 5  # dòng 'RQ1 ...' ngắn hơn mức này là nhắc tới RQ, không phải định nghĩa
SIMILARITY_FLOOR = 0.6  # Jaccard theo từ; thấp hơn coi là hai câu hỏi khác nhau

_HEAD_RE = re.compile(r"^(#{1,4})\s+(.*)$", re.MULTILINE)
_RQ_LINE_RE = re.compile(
    r"^(?P<lead>\s*(?:[-*]\s+|\d+[.)]\s+)?(?:\*\*)?RQ\s?(?P<n>\d+)\s*(?:[.:)])?(?:\*\*)?(?:\s*[.:])?\s*)(?P<body>\S.*)$",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _sections(text: str) -> list[tuple[str, int, int]]:
    """(tiêu đề thường, vị trí đầu thân, vị trí cuối thân) của mọi mục."""
    heads = list(_HEAD_RE.finditer(text))
    return [
        (h.group(2).strip().lower(), h.end(), heads[i + 1].start() if i + 1 < len(heads) else len(text))
        for i, h in enumerate(heads)
    ]


def _is_rq_section(title: str) -> bool:
    return "research question" in title


def parse_rq_lines(chunk: str) -> list[tuple[int, str]]:
    """[(số RQ, nội dung)] cho các dòng định nghĩa RQ trong một đoạn văn bản."""
    out: list[tuple[int, str]] = []
    for line in chunk.splitlines():
        m = _RQ_LINE_RE.match(line)
        if m and len(m.group("body").split()) >= MIN_BODY_WORDS:
            out.append((int(m.group("n")), m.group("body").strip()))
    return out


def section_rqs(text: str) -> dict[str, list[tuple[int, str]]]:
    """Định nghĩa RQ theo từng mục có 'Research Questions' trong tiêu đề (khóa = tiêu đề thường)."""
    result: dict[str, list[tuple[int, str]]] = {}
    for title, start, end in _sections(text):
        if _is_rq_section(title):
            rqs = parse_rq_lines(text[start:end])
            if rqs:
                result[title] = rqs
    return result


def canonical_rqs(source: str) -> list[str]:
    """Danh sách RQ chuẩn (theo thứ tự RQ1, RQ2...) đọc từ blueprint hoặc từ một mục; rỗng nếu không đủ."""
    seen: dict[int, str] = {}
    for n, body in parse_rq_lines(source):
        seen.setdefault(n, body)
    ordered = [seen[n] for n in sorted(seen)]
    return ordered if len(ordered) >= MIN_RQS and sorted(seen) == list(range(1, len(seen) + 1)) else []


def rq_block(canonical: list[str]) -> str:
    """Đoạn đưa vào prompt các chặng: RQ chuẩn, bắt buộc dùng nguyên văn và trả lời đủ ở phần kết."""
    if not canonical:
        return ""
    lines = "\n".join(f"RQ{i}. {q}" for i, q in enumerate(canonical, start=1))
    return (
        "CANONICAL RESEARCH QUESTIONS (single source of truth):\n"
        f"{lines}\n"
        "List these questions exactly once, in the Introduction, with the same numbers and wording. Never add, drop, "
        "reorder or rephrase them, and never list them again in any later section (Review Methodology, Discussion, "
        f"Conclusion): there refer to them only as RQ1...RQ{len(canonical)}, and the Conclusion must answer every one of them."
    )


def enforce_rqs(text: str, canonical: list[str]) -> str:
    """Ghi đè nội dung dòng RQ trong mọi mục 'Research Questions' bằng RQ chuẩn khi số dòng khớp đúng số RQ chuẩn."""
    if not canonical:
        return text
    pieces: list[str] = []
    pos = 0
    for title, start, end in _sections(text):
        if not _is_rq_section(title):
            continue
        chunk = text[start:end]
        lines = chunk.splitlines(keepends=True)
        idx = [i for i, ln in enumerate(lines) if (m := _RQ_LINE_RE.match(ln.rstrip("\r\n"))) and len(m.group("body").split()) >= MIN_BODY_WORDS]
        if len(idx) != len(canonical):
            continue
        for k, i in enumerate(idx):
            raw = lines[i]
            ending = raw[len(raw.rstrip("\r\n")):]
            m = _RQ_LINE_RE.match(raw.rstrip("\r\n"))
            lines[i] = f"{m.group('lead')}{canonical[k]}{ending}"
        pieces.append(text[pos:start])
        pieces.append("".join(lines))
        pos = end
    pieces.append(text[pos:])
    return "".join(pieces)


def _tokens(s: str) -> set[str]:
    return set(_WORD_RE.findall(s.lower()))


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= SIMILARITY_FLOOR


def check_rq_definitions(text: str) -> list[str]:
    """Lỗi khi các mục định nghĩa RQ (vd. 1.3 và 2.1) có số RQ hoặc nội dung khác nhau."""
    sections = list(section_rqs(text).items())
    if len(sections) < 2:
        return []
    base_title, base = sections[0]
    base_map = dict(base)
    problems: list[str] = []
    for title, rqs in sections[1:]:
        other = dict(rqs)
        if set(other) != set(base_map):
            problems.append(f"RQ định nghĩa không nhất quán: mục '{base_title}' có RQ{sorted(base_map)} nhưng mục '{title}' có RQ{sorted(other)}")
            continue
        for n in sorted(base_map):
            if not _similar(base_map[n], other[n]):
                problems.append(f"RQ{n} được định nghĩa khác nhau giữa mục '{base_title}' và '{title}'")
    return problems


_NUM_HEAD_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")
_NON_BODY_TITLE_RE = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:references|bibliography)\b")
_FENCE_SPAN_RE = re.compile(r"```.*?```", re.DOTALL)


def _rq_homes(text: str) -> tuple[int, dict[int, str], list[tuple[str, int, int]]]:
    """(chỉ số mục 'gốc' định nghĩa RQ đầu tiên, RQ của mục gốc, danh sách mục thân bài). Gốc = -1 khi không có."""
    fences = [(m.start(), m.end()) for m in _FENCE_SPAN_RE.finditer(text)]
    secs = []
    for title, start, end in _sections(text):
        if _NON_BODY_TITLE_RE.match(title):
            break
        if any(a <= start < b for a, b in fences):
            continue
        secs.append((title, start, end))
    for i, (_title, start, end) in enumerate(secs):
        rqs = parse_rq_lines(_FENCE_SPAN_RE.sub("", text[start:end]))
        if len({n for n, _ in rqs}) >= MIN_RQS:
            return i, dict(rqs), secs
    return -1, {}, secs


def _is_repeat(n: int, body: str, home: dict[int, str]) -> bool:
    """Dòng RQ ở mục khác là định nghĩa lặp khi giống RQ gốc cùng số, hoặc chỉ là câu hỏi (kết thúc '?').

    Dòng trả lời ('RQ1: Transformers outperform ...') không bị coi là lặp.
    """
    return n in home and (_similar(body, home[n]) or body.rstrip(" *").endswith("?"))


def _repeat_lines(chunk: str, home: dict[int, str]) -> list[int]:
    out = []
    for i, line in enumerate(chunk.splitlines()):
        m = _RQ_LINE_RE.match(line)
        if m and len(m.group("body").split()) >= MIN_BODY_WORDS and _is_repeat(int(m.group("n")), m.group("body"), home):
            out.append(i)
    return out


def check_rq_repetition(text: str) -> list[str]:
    """Lỗi khi danh sách RQ được nêu lại nguyên văn ở mục khác ngoài mục định nghĩa đầu tiên (thường là Introduction)."""
    home_idx, home, secs = _rq_homes(text)
    if home_idx < 0:
        return []
    home_title = secs[home_idx][0]
    return [
        f"RQ được định nghĩa lặp ở mục '{title}' (đã nêu ở '{home_title}'); chỉ nêu một lần, các mục sau gọi RQ1..RQn"
        for title, start, end in secs[home_idx + 1 :]
        if _repeat_lines(_FENCE_SPAN_RE.sub("", text[start:end]), home)
    ]


def dedupe_rq_definitions(text: str) -> tuple[str, list[str]]:
    """Giữ định nghĩa RQ ở mục đầu tiên; ở mục sau thay các dòng RQ lặp bằng một câu tham chiếu. Trả về (văn bản, mục đã sửa)."""
    home_idx, home, secs = _rq_homes(text)
    if home_idx < 0:
        return text, []
    home_title = secs[home_idx][0]
    num = _NUM_HEAD_RE.match(home_title)
    where = f"Section {num.group(1)}" if num else "the Introduction"
    last = max(home)
    ref_line = f"This review addresses research questions RQ1–RQ{last} as stated in {where}."
    pieces: list[str] = []
    pos = 0
    changed: list[str] = []
    for title, start, end in secs[home_idx + 1 :]:
        chunk = text[start:end]
        if _FENCE_SPAN_RE.search(chunk):
            continue  # mục có khối code/biểu đồ: không đụng để tránh lệch dòng
        idx = _repeat_lines(chunk, home)
        if not idx:
            continue
        lines = chunk.splitlines(keepends=True)
        ending = lines[idx[0]][len(lines[idx[0]].rstrip("\r\n")):] or "\n"
        lines[idx[0]] = ref_line + ending
        for i in reversed(idx[1:]):
            del lines[i]
        pieces += [text[pos:start], "".join(lines)]
        pos = end
        changed.append(title)
    pieces.append(text[pos:])
    return "".join(pieces), changed
