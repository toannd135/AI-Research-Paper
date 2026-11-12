"""Phase 3 — kiểm tra nhất quán khoa học bằng luật (không LLM). Chỉ trả cảnh báo (WARNING), không sửa văn bản.

Kiểm tra: RQ Intro↔Conclusion, tên method theo [n] giữa các bảng, biến thể tên dataset, số trong Abstract có trong thân bài,
độ dài Abstract (150–220 từ), đánh số Table/Figure, cân bằng công thức LaTeX, cột Dice trộn thang tỷ lệ (0–1) và % (0–100).
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.domains import is_mri

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


_ABSTRACT_PARTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("phương pháp review (nguồn, cách chọn/phân tích corpus)", re.compile(r"\b(?:we (?:review|survey|analy[sz]e|synthesi[sz]e|compare|examine)|corpus|literature|reviewed|search(?:ed)?|selected|inclusion)\b", re.I)),
    ("số paper/nghiên cứu được review", re.compile(r"\b\d{1,4}\s+(?:\w+\s+){0,3}(?:papers?|studies|works|articles|publications|methods)\b", re.I)),
    ("phát hiện định lượng chính", re.compile(r"\d+(?:\.\d+)?\s*%|\b(?:AUC|AUROC|EER|Dice|HD95|accuracy|F1)\b[^.]{0,40}\d|\d[^.]{0,40}\b(?:AUC|AUROC|EER|Dice|HD95|accuracy|F1)\b", re.I)),
    ("đóng góp/điểm mới", re.compile(r"\b(?:contribut\w*|taxonomy|framework|we (?:propose|introduce|present)|novel|first)\b", re.I)),
)


def _check_abstract_content(secs: dict[str, str]) -> list[str]:
    """Abstract phải nêu phương pháp review, số paper, phát hiện định lượng chính và đóng góp (kiểm bằng luật, chỉ cảnh báo)."""
    abstract = secs.get("abstract")
    if abstract is None:
        return []
    return [f"Abstract chưa nêu rõ {label}" for label, rx in _ABSTRACT_PARTS if not rx.search(abstract)]


_ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,5}(?:\+\+)?\b")
_ACRONYM_IGNORE = frozenset({"RQ", "II", "III", "IV", "VI", "IEEE", "PDF", "CVPR", "ICCV", "ECCV", "NIPS", "AAAI", "ACM", "DOI", "URL", "NR", "AND", "FOR", "THE", "TABLE", "FIGURE", "ARXIV", "ICML", "ICLR", "ACL", "OK", "US", "UK", "ID"})
_ABBREV_SECTION_RE = re.compile(r"abbreviation|acronym|nomenclature|list of symbols", re.I)
ACRONYM_MIN_USES = 3
ACRONYM_TABLE_MIN = 8


def check_acronyms(text: str) -> list[str]:
    """Viết tắt dùng nhiều lần mà chưa từng được định nghĩa dạng 'Expanded Form (ACR)'; thiếu bảng viết tắt khi có nhiều viết tắt."""
    body = re.split(r"\n#{1,3}\s*References\b", text, maxsplit=1)[0]
    body = _FENCE_RE.sub("", body)
    counts: dict[str, int] = {}
    for m in _ACRONYM_RE.finditer(body):
        if m.group(0) not in _ACRONYM_IGNORE and not m.group(0).isdigit():
            counts[m.group(0)] = counts.get(m.group(0), 0) + 1
    frequent = {a: n for a, n in counts.items() if n >= ACRONYM_MIN_USES}
    out = [
        f"viết tắt {a} dùng {n} lần nhưng chưa được định nghĩa lần đầu dạng 'Tên đầy đủ ({a})'"
        for a, n in sorted(frequent.items(), key=lambda kv: -kv[1])
        if not re.search(rf"\(\s*{re.escape(a)}\s*\)", body)
    ]
    has_table = any(_ABBREV_SECTION_RE.search(h) for h in _sections(text))
    if len(frequent) >= ACRONYM_TABLE_MIN and not has_table:
        out.append(f"có {len(frequent)} viết tắt nhưng không có mục/bảng danh sách viết tắt (Abbreviations)")
    return out


def check_consistency(text: str) -> list[str]:
    secs = _sections(text)
    return (
        _check_rq(secs)
        + _check_names_and_datasets(text)
        + _check_abstract(secs, text)
        + _check_abstract_content(secs)
        + check_acronyms(text)
        + _check_numbering(text)
        + _check_formulas(text)
        + (_check_dice_scale(text) if is_mri() else [])
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


_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_AXIS_COUNT_RE = re.compile(r"\b(one|two|three|four|five|six|seven|eight|\d)\b[\s-]+(?:[\w-]+\s+){0,3}?axes\b|\b(one|two|three|four|five|six|seven|eight|\d)[\s-]+axis\b", re.I)


def check_axis_count(text: str) -> list[str]:
    """Số trục taxonomy được nêu ở các chỗ khác nhau (Abstract/Contributions/mục taxonomy) phải trùng nhau."""
    body = _FENCE_RE.sub("", text.split("\n## References", 1)[0])
    found: dict[int, str] = {}
    for m in _AXIS_COUNT_RE.finditer(body):
        raw = (m.group(1) or m.group(2)).lower()
        n = _NUM_WORDS.get(raw) or int(raw)
        found.setdefault(n, m.group(0))
    if len(found) < 2:
        return []
    detail = "; ".join(f"{n} trục ('{ex}')" for n, ex in sorted(found.items()))
    return [f"số trục taxonomy không nhất quán giữa các phần: {detail}"]


_LEDGER_WORD_RE = re.compile(r"\b(?:records?|ledger|verified (?:Dice|HD95|values?)|benchmark matri(?:x|ces))\b", re.I)
_MISSING_CFG_RE = re.compile(r"missing[- ]modalit(?:y|ies)[\w\s-]{0,12}(?:configurations?|settings?|scenarios?|results?|records?)", re.I)


def check_ledger_claims(text: str, missing_groups: int) -> list[str]:
    """Bài khẳng định bản ghi/ledger có cấu hình missing-modality trong khi sổ cái không có nhóm missing-modality nào."""
    if missing_groups > 0:
        return []
    body = _FENCE_RE.sub("", text.split("\n## References", 1)[0])
    problems = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
        if _LEDGER_WORD_RE.search(sentence) and _MISSING_CFG_RE.search(sentence) and not _NEGATION_RE.search(sentence):
            problems.append(f"'{sentence.strip()[:140]}'")
    return problems[:5]


_FIRST_NOUNS = r"(?:comprehensive|systematic|large-scale|complete|unified|mapping|survey|review|framework|taxonomy|benchmark|study|work|attempt)"
_FIRST_CLAIM_RE = re.compile(rf"\b(?:the )?first {_FIRST_NOUNS}\b|\bthe first to\b|\bto the best of our knowledge\b[^.]{{0,60}}\bfirst\b", re.I)
# Chỉ tự nhận của bài này mới là tuyên bố tính mới; 'Menze et al. introduced the first BraTS benchmark [3]' là dữ kiện có cite
_SELF_REF_RE = re.compile(r"\b(?:this|our|we|present(?:ed)?\s+(?:work|survey|review|paper|study))\b", re.I)


def novelty_sentences(text: str) -> list[str]:
    """Câu bài TỰ nhận 'first survey/framework/…' (bỏ khối fence, References, câu phủ định)."""
    body = _FENCE_RE.sub("", text.split("\n## References", 1)[0])
    return [
        s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", body)
        if _FIRST_CLAIM_RE.search(s) and _SELF_REF_RE.search(s) and not _NEGATION_RE.search(s)
    ]


def check_novelty_claims(text: str, n_prior_surveys: int | None = None) -> list[str]:
    """Tuyên bố 'first survey/framework …' không thể chứng minh từ một kho PDF cố định → lỗi CHẶN (repair `soften_novelty_claims` chạy trước)."""
    hits = novelty_sentences(text)
    if not hits:
        return []
    extra = f"; kho chỉ có {n_prior_surveys} survey trước để đối chiếu" if n_prior_surveys is not None else ""
    return [f"tuyên bố tính mới chưa kiểm chứng '{h[:140]}'{extra} — hạ xuống đóng góp có phạm vi rõ ràng" for h in hits[:5]]


_DENIAL_RE = re.compile(r"\bno missing[- ]modalit(?:y|ies)\b[\w\s,-]{0,30}(?:results?|records?|evidence|data)\b[^.]{0,80}\b(?:extracted|structured|ledger|records?)\b", re.I)


def check_limitation_denial(text: str, missing_groups: int) -> list[str]:
    """Ngược với check_ledger_claims: sổ cái CÓ nhóm missing-modality nhưng bài lại nói 'chưa trích xuất kết quả missing-modality nào'."""
    if missing_groups <= 0:
        return []
    body = _FENCE_RE.sub("", text.split("\n## References", 1)[0])
    return [f"'{sentence.strip()[:140]}'" for sentence in re.split(r"(?<=[.!?])\s+|\n+", body) if _DENIAL_RE.search(sentence)][:5]


_PRIOR_SURVEY_RE = re.compile(r"\b(?:prior|previous|existing|earlier|recent|related)\s+(?:literature\s+)?(?:surveys?|reviews?)\b", re.I)
_SURVEYLIKE_TITLE_RE = re.compile(r"\b(?:survey|review|overview|state[- ]of[- ]the[- ]art|tutorial|comprehensive|systematic|meta-analysis|taxonomy|literature)\b", re.I)


def check_prior_survey_claims(text: str, titles_by_number: dict[int, str]) -> list[str]:
    """Câu gọi [n] là 'prior survey/review' nhưng tiêu đề nguồn [n] không phải survey (vd. báo cáo challenge BraTS)."""
    body = _FENCE_RE.sub("", text.split("\n## References", 1)[0])
    problems: dict[int, str] = {}
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
        if not _PRIOR_SURVEY_RE.search(sentence) or _NEGATION_RE.search(sentence):
            continue
        for group in re.findall(r"\[([\d,\s–-]+)\]", sentence):
            for part in re.split(r",\s*", group.strip()):
                nums = part.replace("–", "-").split("-")
                if len(nums) == 2 and nums[0].strip().isdigit() and nums[1].strip().isdigit() and int(nums[1]) - int(nums[0]) < 10:
                    rng = range(int(nums[0]), int(nums[1]) + 1)
                elif part.strip().isdigit():
                    rng = [int(part)]
                else:
                    continue
                for n in rng:
                    title = titles_by_number.get(n)
                    if title and not _SURVEYLIKE_TITLE_RE.search(title):
                        problems.setdefault(n, title)
    return [f"[{n}] được gọi là survey/review trước đó nhưng tiêu đề nguồn là '{t[:80]}'" for n, t in sorted(problems.items())]


_OVERGEN_RE = re.compile(
    r"\b(?:most effective|best[- ]performing|state[- ]of[- ]the[- ]art|dominant|superior|outperform\w*)\b[^.]{0,80}"
    r"\b(?:paradigm|approach(?:es)?|strateg(?:y|ies)|family|fusion|methods?|models?)\b[^.]{0,80}"
    r"\b(?:in the field|overall|currently|across (?:all|the)|all (?:15 )?subsets|universally|generally)\b",
    re.I,
)
_SCOPE_RE = re.compile(r"\b(?:within|only (?:for|in|under)|under the|in the setting|protocol of|limited to|restricted to|in this study|of \[\d+\])\b", re.I)


def check_overgeneralization(text: str) -> list[str]:
    """Câu xếp hạng 'paradigm tốt nhất của lĩnh vực' không nêu phạm vi (nghiên cứu/protocol); chỉ cảnh báo."""
    body = _FENCE_RE.sub("", text.split("\n## References", 1)[0])
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
        if _OVERGEN_RE.search(sentence) and not _SCOPE_RE.search(sentence) and not _NEGATION_RE.search(sentence):
            out.append(f"'{sentence.strip()[:140]}'")
    return out[:5]


_URL_ID_RE = re.compile(r"(?:https?://\S+|doi:\S+|arxiv:\s*\S+|\b10\.\d{4,}/\S+)", re.I)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_REF_LINE_RE = re.compile(r"^\s*\[(\d+)\]")


def check_reference_years(text: str) -> list[str]:
    """Mục References ghi hai năm khác nhau trong cùng một dòng (vd. '2024' ... '2022'); chỉ cảnh báo, không tự chọn năm."""
    if "\n## References" not in text:
        return []
    refs = text.split("\n## References", 1)[1]
    out = []
    for line in refs.split("\n"):
        m = _REF_LINE_RE.match(line)
        if not m:
            continue
        years = set(_YEAR_RE.findall(_URL_ID_RE.sub("", line)))
        if len(years) > 1:
            out.append(f"[{m.group(1)}] ghi nhiều năm: {', '.join(sorted(years))}")
    return out[:8]
