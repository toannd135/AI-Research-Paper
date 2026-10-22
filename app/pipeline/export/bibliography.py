"""Tách mục '## References' (IEEE) của báo cáo thành BibTeX và bảng khảo sát tài liệu.

Metadata chỉ gồm những gì pipeline đã lưu (tác giả đầu / et al., tiêu đề, venue, năm, DOI);
không bổ sung thông tin từ nguồn ngoài.
"""

import json
import re

_REF_LINE_RE = re.compile(
    r'^\[(\d+)\]\s+(?P<authors>.*?),\s+"(?P<title>.+?),"\s+\*(?P<venue>.+?)\*,\s+(?P<year>\d{4})'
    r"(?:,\s+DOI:\s*(?P<doi>\S+?))?\.?\s*$"
)
_BIB_SPECIAL = str.maketrans({"&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_"})


def split_references(report_md: str) -> tuple[str, str]:
    body, _, refs = report_md.partition("\n## References")
    return body, refs


def parse_references(report_md: str) -> list[dict]:
    """Các dòng '[n] Authors, "Title," *Venue*, Year, DOI: x.' → list dict; dòng lạ giữ nguyên ở 'raw'."""
    _, refs = split_references(report_md)
    out = []
    for line in refs.splitlines():
        line = line.strip()
        if not re.match(r"^\[\d+\]", line):
            continue
        m = _REF_LINE_RE.match(line)
        if m:
            out.append({"n": int(m.group(1)), **{k: (m.group(k) or "") for k in ("authors", "title", "venue", "year", "doi")}})
        else:
            n = int(re.match(r"^\[(\d+)\]", line).group(1))
            out.append({"n": n, "raw": re.sub(r"^\[\d+\]\s*", "", line)})
    return out


def cite_key(n: int) -> str:
    return f"ref{n}"


def _bib_authors(authors: str) -> str:
    others = bool(re.search(r"\bet al\.?$", authors))
    names = [a.strip() for a in re.split(r"\s+and\s+", re.sub(r"\s*\bet al\.?$", "", authors)) if a.strip()]
    return " and ".join(names + (["others"] if others else []))


def _bib_escape(text: str) -> str:
    return text.translate(_BIB_SPECIAL)


def references_to_bibtex(refs: list[dict]) -> str:
    entries = []
    for r in refs:
        key = cite_key(r["n"])
        if "raw" in r:
            entries.append(f"@misc{{{key},\n  note = {{{_bib_escape(r['raw'])}}}\n}}")
            continue
        preprint = "arxiv" in r["venue"].lower() or "preprint" in r["venue"].lower()
        fields = [
            ("author", _bib_authors(r["authors"])),
            ("title", "{" + _bib_escape(r["title"]) + "}"),  # {{..}} giữ nguyên hoa/thường
            ("howpublished" if preprint else "journal", _bib_escape(r["venue"])),
            ("year", r["year"]),
        ]
        if r["doi"]:
            fields.append(("doi", r["doi"]))
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v)
        entries.append(f"@{'misc' if preprint else 'article'}{{{key},\n{body}\n}}")
    return "\n\n".join(entries) + "\n"


def survey_table_spec(refs: list[dict]) -> dict | None:
    """Bảng khảo sát tài liệu (khối ```table): Ref., Authors, Year, Venue — sắp theo năm."""
    rows = [
        [f"[{r['n']}]", r["authors"], r["year"], r["venue"]]
        for r in sorted((r for r in refs if "raw" not in r), key=lambda r: (r["year"], r["n"]))
    ]
    if not rows:
        return None
    return {"caption": "Summary of the surveyed literature", "columns": ["Ref.", "Authors", "Year", "Venue"], "rows": rows}


def survey_table_block(refs: list[dict]) -> str:
    spec = survey_table_spec(refs)
    return "" if spec is None else "```table\n" + json.dumps(spec, ensure_ascii=False) + "\n```"
