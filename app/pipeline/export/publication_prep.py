"""Dọn report Markdown trước khi dựng LaTeX để nộp bài.

- Chạy lại `finalize_structure` (report cũ sinh trước khi có bước này): đánh số mục, Paper Organization, tham chiếu bản nháp.
- Đánh số lại trích dẫn theo thứ tự xuất hiện (kể cả nhãn trong biểu đồ/bảng JSON) và bỏ mục References không được trích:
  BibTeX kiểu IEEE đánh số theo thứ tự trích dẫn, nên số in sẵn trong hình phải theo cùng thứ tự đó mới khớp.
- Bỏ cụm từ nội bộ của pipeline, danh sách RQ lặp lại.
"""

import re

from app.agent.evidence.report_structure import finalize_structure, strip_dangling_citations

_REFS_HEAD = "\n## References"
_CITE_GROUP_RE = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")
_FENCE_RE = re.compile(r"(```[a-zA-Z0-9_-]*[ \t]*\n.*?```)", re.DOTALL)
_JSON_STR_RE = re.compile(r'"(?:[^"\\\n]|\\.)*"')
_CITING_FENCES = ("```chart", "```table", "```mermaid", "```image")

_INTERNAL_PHRASES = (
    (re.compile(r"\b(?:the\s+)?EVIDENCE LIMITS\b"), "the evidence-extraction limits"),
    (re.compile(r"\s*\(Ours\)"), ""),  # nhãn chép từ bảng của bài gốc, không phải phương pháp của bài này
    (re.compile(r"\bSources?:\s*\.\s*"), ""),
)
_RQ_RE = re.compile(r"^\*\*RQ(\d+)[.:]?\*\*\s*(.+)$", re.MULTILINE)


def _numbers(spec: str) -> list[int]:
    out: list[int] = []
    for part in re.split(r"\s*,\s*", spec):
        m = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", part)
        if m and int(m.group(1)) <= int(m.group(2)) <= int(m.group(1)) + 50:
            out += range(int(m.group(1)), int(m.group(2)) + 1)
        else:
            out += [int(n) for n in re.findall(r"\d+", part)]
    return out


def _citation_spans(body: str):
    """(start, end, numbers) của mọi cụm [n] trong văn xuôi và trong chuỗi JSON/nhãn của khối hình/bảng."""
    pos = 0
    for part in _FENCE_RE.split(body):
        if part.startswith("```"):
            if part.startswith(_CITING_FENCES):
                for s in _JSON_STR_RE.finditer(part):
                    for m in _CITE_GROUP_RE.finditer(s.group(0)):
                        yield pos + s.start() + m.start(), pos + s.start() + m.end(), _numbers(m.group(1))
        else:
            for m in _CITE_GROUP_RE.finditer(part):
                yield pos + m.start(), pos + m.end(), _numbers(m.group(1))
        pos += len(part)


def renumber_citations(report_md: str) -> str:
    """Số trích dẫn mới = thứ tự xuất hiện đầu tiên; mục References không được trích bị bỏ, số không có mục bị xoá."""
    body, sep, refs = report_md.partition(_REFS_HEAD)
    if not sep:
        return report_md
    ref_lines = {int(m.group(1)): m.group(2) for m in re.finditer(r"^\[(\d+)\]\s*(.+)$", refs, re.MULTILINE)}
    if not ref_lines:
        return report_md
    spans = list(_citation_spans(body))
    mapping: dict[int, int] = {}
    for _, _, nums in spans:
        for n in nums:
            if n in ref_lines and n not in mapping:
                mapping[n] = len(mapping) + 1
    out, last = [], 0
    for start, end, nums in spans:
        new = list(dict.fromkeys(mapping[n] for n in nums if n in mapping))
        out.append(body[last:start])
        if new:
            out.append("[" + ", ".join(map(str, new)) + "]")
        else:  # số không có trong References: xoá cả khoảng trắng đứng trước
            out[-1] = out[-1].rstrip(" ")
        last = end
    out.append(body[last:])
    new_body = "".join(out)
    tail = re.sub(r"^\[\d+\]\s*.+$\n?", "", refs, flags=re.MULTILINE).rstrip()
    new_refs = "\n\n".join(f"[{new}] {ref_lines[old]}" for old, new in sorted(mapping.items(), key=lambda kv: kv[1]))
    return f"{new_body}{_REFS_HEAD}{tail}\n\n{new_refs}\n"


def dedupe_research_questions(report_md: str) -> str:
    """Mục 'Research Questions' lặp lại nguyên các RQ đã nêu ở mục trước → thay bằng một câu dẫn chiếu."""
    sections = list(re.finditer(r"^(#{2,3})\s+((\d+(?:\.\d+)?)\.?\s+.*)$", report_md, re.MULTILINE))
    seen: dict[str, str] = {}
    for k, h in enumerate(sections):
        start = h.end()
        end = sections[k + 1].start() if k + 1 < len(sections) else len(report_md)
        chunk = report_md[start:end]
        rqs = [(n, re.sub(r"\s+", " ", t).strip().lower()) for n, t in _RQ_RE.findall(chunk)]
        if not rqs:
            continue
        if all(t in seen for _, t in rqs) and not re.sub(_RQ_RE, "", chunk).strip():
            first = seen[rqs[0][1]]
            nums = sorted(int(n) for n, _ in rqs)
            sentence = (f"\n\nThe review is guided by the research questions RQ{nums[0]}–RQ{nums[-1]} stated in Section {first}; "
                        "the methodology below describes how evidence for each question was collected and assessed.\n\n")
            return report_md[:start] + sentence + report_md[end:].lstrip("\n")
        for _, t in rqs:
            seen.setdefault(t, h.group(3))
    return report_md


def prepare_report_for_latex(report_md: str) -> str:
    text = finalize_structure(report_md)
    max_ref = max((int(n) for n in re.findall(r"^\[(\d+)\]", report_md.partition(_REFS_HEAD)[2], re.MULTILINE)), default=0)
    if max_ref:
        text, _ = strip_dangling_citations(text, max_ref)
    body, sep, refs = text.partition(_REFS_HEAD)
    for rx, repl in _INTERNAL_PHRASES:
        body = rx.sub(repl, body)
    text = dedupe_research_questions(body) + sep + refs
    return renumber_citations(text)
