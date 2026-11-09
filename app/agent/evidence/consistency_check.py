"""Phase 3 — kiểm tra nhất quán khoa học bằng luật (không LLM). Chỉ trả cảnh báo (WARNING), không sửa văn bản.

Kiểm tra: RQ Intro↔Conclusion, tên method theo [n] giữa các bảng, biến thể tên dataset, số trong Abstract có trong thân bài,
độ dài Abstract (150–220 từ), đánh số Table/Figure, cân bằng công thức LaTeX, cột Dice trộn thang tỷ lệ (0–1) và % (0–100).
"""

from __future__ import annotations

import json
import re
from typing import Any

ABSTRACT_WORDS = (150, 220)
_FENCE_RE = re.compile(r"```(mermaid|chart|image|table)[ \t]*\n(.*?)```", re.DOTALL)
_HEAD_RE = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)
_RQ_RE = re.compile(r"\bRQ\s*(\d+)\b", re.I)
_NUM_RE = re.compile(r"\d+\.\d+|\d{2,}")
_CITE_RE = re.compile(r"\[(\d+)\]")
_CAPTION_RE = {"Table": re.compile(r"^\**\s*Table\s+(\d+)\s*[:.]", re.I | re.M), "Figure": re.compile(r"^\**\s*(?:Figure|Fig\.)\s+(\d+)\s*[:.]", re.I | re.M)}


def _sections(text: str) -> dict[str, str]:
    heads = list(_HEAD_RE.finditer(text))
    out: dict[str, str] = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.setdefault(h.group(2).strip().lower(), text[h.end() : end])
    return out


def _section_like(secs: dict[str, str], *keys: str) -> str:
    return "\n".join(body for name, body in secs.items() if any(k in name for k in keys))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _tables(text: str) -> list[dict[str, Any]]:
    out = []
    for m in _FENCE_RE.finditer(text):
        if m.group(1) == "table":
            try:
                spec = json.loads(m.group(2))
            except ValueError:
                continue
            if isinstance(spec, dict):
                out.append(spec)
    return out


def _check_rq(secs: dict[str, str]) -> list[str]:
    intro = {int(x) for x in _RQ_RE.findall(_section_like(secs, "introduction", "research questions"))}
    concl = {int(x) for x in _RQ_RE.findall(_section_like(secs, "conclusion"))}
    if not intro or not concl:
        return []
    missing = sorted(intro - concl)
    extra = sorted(concl - intro)
    out = []
    if missing:
        out.append(f"RQ{missing} nêu ở phần mở đầu nhưng Conclusion không trả lời")
    if extra:
        out.append(f"RQ{extra} xuất hiện ở Conclusion nhưng không được đặt ra ở phần mở đầu")
    return out


def _check_names_and_datasets(text: str) -> list[str]:
    names: dict[int, set[str]] = {}
    datasets: dict[str, set[str]] = {}
    for spec in _tables(text):
        cols = [str(c).lower() for c in spec.get("columns", [])]
        for row in spec.get("rows") or []:
            if not isinstance(row, list):
                continue
            for j, cell in enumerate(row):
                col = cols[j] if j < len(cols) else ""
                if "dataset" in col:
                    for part in re.split(r"[/,;]", str(cell)):
                        if part.strip() and part.strip() not in ("–", "NR"):
                            datasets.setdefault(_norm(part), set()).add(part.strip())
                if "method" in col:
                    cites = [int(n) for n in _CITE_RE.findall(str(cell))]
                    label = _CITE_RE.sub("", str(cell)).replace("*", "").strip()
                    if len(cites) == 1 and label:
                        names.setdefault(cites[0], set()).add(label)
    out = [f"tên method khác nhau cho cùng nguồn [{n}] giữa các bảng: {sorted(v)}" for n, v in names.items() if len({_norm(x) for x in v}) > 1]
    out += [f"dataset viết không nhất quán giữa các bảng: {sorted(v)}" for v in datasets.values() if len(v) > 1]
    return out


def _check_abstract(secs: dict[str, str], text: str) -> list[str]:
    abstract = secs.get("abstract")
    if abstract is None:
        return []
    out = []
    words = len(re.findall(r"\b[\w'-]+\b", abstract))
    if not ABSTRACT_WORDS[0] <= words <= ABSTRACT_WORDS[1]:
        out.append(f"Abstract {words} từ, ngoài khoảng {ABSTRACT_WORDS[0]}–{ABSTRACT_WORDS[1]}")
    body = text.replace(abstract, "", 1)
    body_nums = set(_NUM_RE.findall(body))
    missing = sorted({x for x in _NUM_RE.findall(abstract) if x not in body_nums})
    if missing:
        out.append(f"số trong Abstract không xuất hiện ở thân bài: {missing[:8]}")
    return out


def _check_numbering(text: str) -> list[str]:
    out = []
    body = _FENCE_RE.sub("", text)
    for label, rx in _CAPTION_RE.items():
        nums = [int(x) for x in rx.findall(body)]
        if nums and (len(nums) != len(set(nums)) or sorted(set(nums)) != list(range(1, max(nums) + 1))):
            out.append(f"đánh số {label} caption không liên tục/trùng: {nums}")
    return out


def _check_formulas(text: str) -> list[str]:
    body = _FENCE_RE.sub("", text)
    out = []
    flat = body.replace("\\$", "")
    if flat.count("$") % 2:
        out.append("số dấu $ của công thức không chẵn (công thức bị mở mà không đóng)")
    for m in re.finditer(r"\$\$(.+?)\$\$|\$([^$\n]+)\$", flat, re.DOTALL):
        f = m.group(1) or m.group(2)
        if f.count("{") != f.count("}"):
            out.append(f"công thức lệch ngoặc nhọn: {f.strip()[:60]}")
            break
    for env in set(re.findall(r"\\begin\{(\w+\*?)\}", flat)):
        if len(re.findall(rf"\\begin\{{{re.escape(env)}\}}", flat)) != len(re.findall(rf"\\end\{{{re.escape(env)}\}}", flat)):
            out.append(f"\\begin/\\end{{{env}}} không cân bằng")
    return out


_DICE_RE = re.compile(r"\b(?:dice|dsc)\b", re.I)
_VALUE_HEAD_RE = re.compile(r"^(?:value|score|result|reported value)s?\b", re.I)
_METRIC_HEAD_RE = re.compile(r"^metric", re.I)
_FIRST_NUM_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)")


def _pipe_tables(text: str) -> list[dict[str, Any]]:
    """Bảng Markdown '| a | b |' ngoài khối rào -> {caption, columns, rows} như bảng JSON."""
    body = _FENCE_RE.sub("", text)
    out: list[dict[str, Any]] = []
    for m in re.finditer(r"((?:^[ \t]*\|.*\|[ \t]*\n?){3,})", body, re.M):
        lines = [ln.strip().strip("|") for ln in m.group(1).strip().splitlines()]
        cells = [[c.strip() for c in ln.split("|")] for ln in lines if not re.fullmatch(r"[\s:|-]+", ln)]
        before = body[: m.start()].rstrip().rsplit("\n", 1)[-1]
        out.append({"caption": before if "Table" in before else "", "columns": cells[0], "rows": cells[1:]})
    return out


def _check_dice_scale(text: str) -> list[str]:
    """Một cột Dice vừa có giá trị ≤1 (tỷ lệ) vừa có giá trị >1 (%) -> người đọc dễ hiểu nhầm; đề nghị tách cột/chuẩn hóa."""
    out = []
    for spec in _tables(text) + _pipe_tables(text):
        cols = [str(c) for c in spec.get("columns") or []]
        rows = [r for r in spec.get("rows") or [] if isinstance(r, list)]
        metric_col = next((i for i, c in enumerate(cols) if _METRIC_HEAD_RE.match(c)), None)
        values: list[float] = []
        for i, col in enumerate(cols):
            per_row_dice = metric_col is not None and _VALUE_HEAD_RE.match(col)
            if not (_DICE_RE.search(col) or per_row_dice):
                continue
            for r in rows:
                if i >= len(r) or (per_row_dice and not _DICE_RE.search(str(r[metric_col]) if metric_col < len(r) else "")):
                    continue
                m = _FIRST_NUM_RE.search(str(r[i]))
                if m:
                    values.append(float(m.group(1)))
        if any(0 < v <= 1 for v in values) and any(v > 1 for v in values):
            cap = str(spec.get("caption") or "").strip("* ")[:80] or "(không caption)"
            out.append(f"bảng '{cap}' trộn Dice dạng tỷ lệ (0–1) và % (0–100) trong cùng cột; tách cột hoặc ghi rõ đơn vị từng dòng")
    return out


def check_consistency(text: str) -> list[str]:
    secs = _sections(text)
    return (
        _check_rq(secs)
        + _check_names_and_datasets(text)
        + _check_abstract(secs, text)
        + _check_numbering(text)
        + _check_formulas(text)
        + _check_dice_scale(text)
    )


_REVIEW_CLAIM_RE = re.compile(r"systematic (?:literature )?review|systematic mapping|\bPRISMA\b", re.IGNORECASE)
_NEGATION_RE = re.compile(r"\b(?:not|no|never|neither|nor|without|isn't|wasn't|weren't|didn't|doesn't|rather than|instead of|non-systematic|unlike)\b", re.IGNORECASE)


_SYSTEMATIC_RE = re.compile(r"systematic (?:literature )?review|systematic mapping", re.IGNORECASE)


def check_review_claims(text: str, declared_type: str | None = None) -> list[str]:
    """Câu khẳng định systematic review/PRISMA mà không có phủ định, khi người dùng KHÔNG khai báo giao thức tương ứng.

    declared_type lấy từ `review_protocol.json` đã hợp lệ: 'systematic' cho phép cả hai; 'scoping' cho phép PRISMA(-ScR) nhưng
    không cho tự nhận systematic review; không khai báo/'narrative' → chỉ là narrative review trên kho PDF nội bộ.
    """
    if declared_type == "systematic":
        return []
    claim_re = _SYSTEMATIC_RE if declared_type == "scoping" else _REVIEW_CLAIM_RE
    body = _FENCE_RE.sub("", text.split("\n## References", 1)[0])
    problems: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
        if claim_re.search(sentence) and not _NEGATION_RE.search(sentence):
            problems.append(f"'{sentence.strip()[:120]}'")
    return problems[:5]


_PAPER_COUNT_RE = re.compile(
    r"\b(\d{1,4})\s+(?:distinct\s+|unique\s+|included\s+|primary\s+|reviewed\s+|retrieved\s+|surveyed\s+|selected\s+)?"
    r"(?:papers|studies|articles|publications|works|sources)\b",
    re.I,
)


def check_paper_counts(text: str, max_papers: int) -> list[str]:
    """'N papers/studies' với N lớn hơn số paper thật trong kho/evidence (vd. LLM suy '73 papers' từ chỉ số [73] của đoạn trích)."""
    if max_papers <= 0:
        return []
    body = _FENCE_RE.sub("", text.split("\n## References", 1)[0])
    bad = sorted({int(m.group(1)) for m in _PAPER_COUNT_RE.finditer(body) if int(m.group(1)) > max_papers})
    return [f"bài nói {n} paper/nghiên cứu nhưng kho chỉ có {max_papers} paper" for n in bad]
