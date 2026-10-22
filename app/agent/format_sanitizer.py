"""Bộ chuẩn hóa và sửa lỗi định dạng tự động cho báo cáo khoa học (Markdown, Mermaid, LaTeX, Code blocks).

Tự động khắc phục các lỗi kinh điển khi LLM sinh định dạng:
1. Mermaid: Sửa nhãn node không bọc ngoặc kép, chứa '\\n', chứa ký tự đặc biệt { }, ( ), ||, sửa subgraph và edge syntax.
2. LaTeX Math: Chuẩn hóa khối display math $$...$$ tách biệt trên dòng riêng và cách dòng trống để KaTeX/MathJax render chuẩn 100%.
3. Algorithm Blocks: Đảm bảo code block thuật toán luôn có tag ```python thay vì ```text hoặc thiếu tag.
4. Authors & Affiliations: Loại bỏ các nhãn placeholder dạng [Author Names], [Institutional Affiliation].
"""

from __future__ import annotations

import re

# Regex tìm khối mermaid
_MERMAID_BLOCK_RE = re.compile(r"```mermaid[ \t]*\n(.*?)```", re.DOTALL)


def _clean_mermaid_label(raw: str) -> str:
    """Làm sạch nội dung label bên trong node Mermaid."""
    s = raw.strip()
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1]
    elif s.startswith("'") and s.endswith("'") and len(s) >= 2:
        s = s[1:-1]

    # Preserve LaTeX groups and commands (including \nabla) inside math labels.
    math_parts: list[str] = []
    def keep_math(match: re.Match) -> str:
        math_parts.append(match.group(0))
        return f"PAPERAIMATHLABEL{len(math_parts) - 1}END"
    s = re.sub(r"(?<!\\)(\${1,2})(.+?)(?<!\\)\1", keep_math, s, flags=re.DOTALL)

    # Thay thế ký tự xuống dòng
    s = s.replace(r"\n", "<br/>").replace("\n", "<br/>")
    # Thay thế ngoặc nhọn để tránh conflict syntax
    s = s.replace("{", "(").replace("}", ")")
    # Thay ngoặc kép bên trong thành nháy đơn
    s = s.replace('"', "'")
    # Thay toán tử || tránh xung đột nhãn cạnh
    s = s.replace("||", "‖")
    for index, formula in enumerate(math_parts):
        s = s.replace(f"PAPERAIMATHLABEL{index}END", formula)
    return s


def sanitize_mermaid_block(mermaid_code: str) -> str:
    """Chuẩn hóa cú pháp sơ đồ Mermaid để render an toàn trong mọi markdown viewer."""
    lines = mermaid_code.split("\n")
    sanitized_lines = []

    for line in lines:
        stripped = line.strip()

        # Bỏ qua dòng trống, khai báo graph/flowchart, classDef, style, class
        if not stripped:
            sanitized_lines.append(line)
            continue

        if any(stripped.startswith(k) for k in ("graph ", "flowchart ", "classDef ", "style ", "class ", "%%", "click ", "linkStyle ")):
            sanitized_lines.append(line)
            continue

        indent = line[: len(line) - len(line.lstrip())]

        # 1. Chuẩn hóa subgraph: `subgraph ID[Title...]` hoặc `subgraph ID Title...`
        sub_bracket_match = re.match(r"^subgraph\s+([A-Za-z0-9_]+)\s*\[(.*)\]$", stripped)
        if sub_bracket_match:
            sub_id = sub_bracket_match.group(1)
            raw_title = sub_bracket_match.group(2).strip().strip('"').strip("'")
            clean_title = raw_title.replace(r"\n", " ").replace('"', "'")
            sanitized_lines.append(f'{indent}subgraph {sub_id} ["{clean_title}"]')
            continue

        sub_plain_match = re.match(r"^subgraph\s+([A-Za-z0-9_]+)\s+([A-Za-z0-9_].*)$", stripped)
        if sub_plain_match and not sub_plain_match.group(2).startswith("["):
            sub_id = sub_plain_match.group(1)
            raw_title = sub_plain_match.group(2).strip().strip('"').strip("'")
            clean_title = raw_title.replace(r"\n", " ").replace('"', "'")
            sanitized_lines.append(f'{indent}subgraph {sub_id} ["{clean_title}"]')
            continue

        if stripped == "end":
            sanitized_lines.append(line)
            continue

        processed_line = line

        # 2. Chuẩn hóa các đường nối có nhãn lỗi:
        # `NodeA -- Label --> NodeB` -> `NodeA -->|"Label"| NodeB`
        processed_line = re.sub(
            r"\s*--\s*(?:\"([^\"]+)\"|([^-\n>]+))\s*-->\s*",
            lambda m: f' -->|"{_clean_mermaid_label(m.group(1) or m.group(2))}"| ',
            processed_line,
        )

        # Chuẩn hóa nhãn cạnh: `-->|Label|` -> `-->|"Label"|` nếu chưa có ngoặc kép
        processed_line = re.sub(
            r"-->\|([^\"\|\n]+)\|",
            lambda m: f'-->|"{_clean_mermaid_label(m.group(1))}"|',
            processed_line,
        )

        # 3. Chuẩn hóa các node định nghĩa (sử dụng lookahead để bao quát cả nhãn có ngoặc lồng nhau)
        delim_lookahead = r"(?=\s*(?:-->|---|==>|\.->|;|\n|$))"

        # - Stadium: NodeId(["..."]) hoặc NodeId([...])
        processed_line = re.sub(
            r"\b([A-Za-z0-9_]+)\(\[(.+?)\]\)" + delim_lookahead,
            lambda m: f'{m.group(1)}(["{_clean_mermaid_label(m.group(2))}"])',
            processed_line,
        )
        # - Cylinder: NodeId[(...)]
        processed_line = re.sub(
            r"\b([A-Za-z0-9_]+)\[\((.+?)\)\]" + delim_lookahead,
            lambda m: f'{m.group(1)}[("{_clean_mermaid_label(m.group(2))}")]',
            processed_line,
        )
        # - Circle: NodeId((...))
        processed_line = re.sub(
            r"\b([A-Za-z0-9_]+)\(\((.+?)\)\)" + delim_lookahead,
            lambda m: f'{m.group(1)}(("{_clean_mermaid_label(m.group(2))}"))',
            processed_line,
        )
        # - Rhombus/Decision: NodeId{...}
        processed_line = re.sub(
            r"\b([A-Za-z0-9_]+)\{(.+?)\}" + delim_lookahead,
            lambda m: f'{m.group(1)}{{"{_clean_mermaid_label(m.group(2))}"}}',
            processed_line,
        )
        # - Rectangle: NodeId[...] (chỉ khi không phải [( )])
        processed_line = re.sub(
            r"\b([A-Za-z0-9_]+)\[(?!\()(.+?)\]" + delim_lookahead,
            lambda m: f'{m.group(1)}["{_clean_mermaid_label(m.group(2))}"]',
            processed_line,
        )

        sanitized_lines.append(processed_line)

    return "\n".join(sanitized_lines)


def sanitize_latex_math(text: str) -> str:
    """Chuẩn hóa các công thức LaTeX display math $$...$$ để KaTeX/MathJax render chuẩn 100%."""
    if "$$" not in text:
        return text

    # 1. Tách dòng cho các môi trường aligned, cases, v.v.
    text = re.sub(r"\$\$\s*(\\begin\{[a-zA-Z*]+\})", r"$$\n\1", text)
    text = re.sub(r"(\\end\{[a-zA-Z*]+\})\s*\$\$", r"\1\n$$", text)

    # 2. Chuẩn hóa mọi khối display math $$...$$ thành block chuẩn:
    # \n\n$$
    # formula
    # $$\n\n
    def _repl_display_math(match: re.Match) -> str:
        body = match.group(1).strip()
        return f"\n\n$$\n{body}\n$$\n\n"

    # Match bất kỳ khối $$...$$ nào
    text = re.sub(r"(?:^|\n)[ \t]*\$\$(.*?)\$\$(?:\n|$)", _repl_display_math, text, flags=re.DOTALL)

    # 3. Thu gọn các khoảng trắng thừa
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def sanitize_code_and_algorithm_blocks(text: str) -> str:
    """Đảm bảo khối Algorithm được gắn tag ```python hoặc ```pseudo chuẩn xác."""
    text = re.sub(
        r"(\*\*Algorithm\s+\d+[^:*]*:?[^\n]*\*\*\s*\n+)```(?:text|plain)?\s*\n",
        r"\1```python\n",
        text,
        flags=re.IGNORECASE,
    )
    return text


def sanitize_author_placeholders(text: str) -> str:
    """Loại bỏ các nhãn giữ chỗ tác giả và viện nghiên cứu nếu LLM sinh ra."""
    text = re.sub(
        r"\*\*Authors:\*\*\s*\[(?:Author Names|Tên tác giả|.*?)\]",
        "**Authors:** PaperAI Automated Research Protocol",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\*\*Affiliations:\*\*\s*\[(?:Institutional Affiliation|Viện nghiên cứu|.*?)\]",
        "**Affiliations:** Open-Source Automated Science Initiative",
        text,
        flags=re.IGNORECASE,
    )
    return text


_INLINE_MATH_SPAN_RE = re.compile(r"(?<![\\$])\$(?!\$)([^$\n]+?)(?<![\\$])\$(?!\$)")


def sanitize_table_math_pipes(text: str) -> str:
    """'|' trong công thức ở hàng bảng (vd. $|x-y|$) bị tách thành ô mới → đổi thành \\vert.

    Bỏ qua '|' có khoảng trắng hai bên: đó là dấu phân cột giữa hai ký hiệu '$' tiền tệ bị ghép nhầm thành một cặp.
    """

    def fix_row(line: str) -> str:
        if not line.lstrip().startswith("|"):
            return line
        return _INLINE_MATH_SPAN_RE.sub(lambda m: "$" + re.sub(r"(?<!\\)(?<!\s)\||(?<!\\)\|(?!\s)", r"\\vert ", m.group(1)) + "$", line)

    return "\n".join(fix_row(line) for line in text.split("\n"))


_PADDED_MATH_RE = re.compile(r"(?<![^\s(\[|,;:>\-])\$(?!\$)[ \t]+([^$\n]+?)[ \t]*(?<![\\$])\$(?!\$)")


_CURRENCY_HINT_RE = re.compile(r"(?<!\\)\$\d")  # '$0.15/M' có thể là tiền tệ: không đoán ghép cặp $ trong dòng này


def sanitize_padded_inline_math(text: str) -> str:
    """Hàng bảng: '$ x $' → '$x$'. KaTeX auto-render ghép '$ H_0 $) | Alt ($ H_1 $' thành một công thức xuyên ô.

    Chỉ áp cho hàng bảng; $ mở phải đứng sau khoảng trắng / dấu mở / đầu dòng, nếu không đó là $ đóng của công thức khác.
    """
    return "\n".join(
        _PADDED_MATH_RE.sub(lambda m: "$" + m.group(1) + "$", line) if line.lstrip().startswith("|") and not _CURRENCY_HINT_RE.search(line) else line
        for line in text.split("\n")
    )


_RAW_REF_RE = re.compile(r'^\[(\d+)\]\s+(?P<head>.*?),\s*Page:\s*[^,]*,\s*Section:.*?[—-]\s*"(?P<snippet>.*)"\s*$')


def sanitize_raw_references(text: str) -> str:
    """Dòng References còn là snippet thô ('…, Page: 1, Section: … — "Title: … Authors: …"') → '[n] Authors, "Title," *Venue*, Year.'

    Chỉ dùng thông tin có trong snippet; thiếu năm thì ghi n.d. thay vì đoán.
    """
    from app.agent.evidence.citation_cleaner import _extract_citation_metadata

    body, sep, refs = text.partition("\n## References")
    if not sep:
        return text
    out = []
    for line in refs.split("\n"):
        m = _RAW_REF_RE.match(line.strip())
        if not m:
            out.append(line)
            continue
        snippet = m.group("snippet")
        meta = _extract_citation_metadata(m.group("head"), snippet)
        year = meta["year"] if re.search(r"\b(?:19|20)\d{2}\b", snippet) else "n.d."
        authors = meta["authors"] if re.search(r"Authors:", snippet, re.IGNORECASE) else "Anonymous"
        doi = f", DOI: {meta['doi'].rstrip('.…')}" if meta["doi"] and not meta["doi"].endswith("...") else ""
        title = meta["title"].rstrip(".…")
        if "..." in authors or "…" in authors:  # snippet cũ bị cắt giữa tên → bỏ phần dở dang
            names = [n.strip() for n in re.split(r",|\s+and\s+", authors) if n.strip() and not re.search(r"\.\.\.|…", n)]
            names = [re.sub(r"\s*et al\.?$", "", n) for n in names]
            authors = (", ".join(names) + " et al.") if names else "Anonymous"
        venue = meta["venue"] if not re.search(r"\.\.\.|…", meta["venue"]) else "Online"
        tail = f"{year}{doi}"
        out.append(f'[{m.group(1)}] {authors}, "{title}," *{venue}*, {tail}{"" if tail.endswith(".") else "."}')
    return body + sep + "\n".join(out)


_REF_LINE_RE = re.compile(r'^\[(\d+)\]\s+.*?"(?P<title>.+?),?"')
_CITE_GROUP_RE = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")
_REMAP_FENCE_RE = re.compile(r"(```.*?```)", re.DOTALL)


def _remap_cites(text: str, mapping: dict[int, int]) -> str:
    def repl(m: re.Match) -> str:
        nums: list[int] = []
        for part in re.split(r"\s*,\s*", m.group(1)):
            r = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", part)
            nums += range(int(r.group(1)), int(r.group(2)) + 1) if r and int(r.group(1)) <= int(r.group(2)) <= int(r.group(1)) + 50 else [int(n) for n in re.findall(r"\d+", part)]
        new = sorted({mapping.get(n, n) for n in nums})
        return "[" + ", ".join(map(str, new)) + "]"

    return _CITE_GROUP_RE.sub(repl, text)


def dedupe_references(text: str) -> str:
    """Gộp các dòng References cùng tiêu đề, đánh số lại tuần tự và cập nhật mọi [n] trong thân bài (kể cả chuỗi trong khối table/chart)."""
    body, sep, refs = text.partition("\n## References")
    if not sep:
        return text
    lines = refs.split("\n")
    seen: dict[str, int] = {}
    mapping: dict[int, int] = {}
    kept: list[str] = []
    for line in lines:
        m = _REF_LINE_RE.match(line.strip())
        if not m:
            kept.append(line)
            continue
        old = int(m.group(1))
        key = " ".join(re.sub(r"[^a-z0-9]+", " ", m.group("title").lower()).split())
        if key in seen:
            mapping[old] = seen[key]
            continue
        seen[key] = mapping[old] = len(seen) + 1
        kept.append(re.sub(r"^\[\d+\]", f"[{mapping[old]}]", line.strip(), count=1))
    if all(k == v for k, v in mapping.items()):
        return text

    def fix_fence(m: re.Match) -> str:
        block = m.group(1)
        kind = re.match(r"```(\w*)", block).group(1)
        if kind in ("table", "chart"):
            return re.sub(r'"(?:[^"\\]|\\.)*"', lambda q: _remap_cites(q.group(0), mapping), block)
        return block

    parts = _REMAP_FENCE_RE.split(body)
    body = "".join(fix_fence(re.match(r"(.*)", p, re.DOTALL)) if i % 2 else _remap_cites(p, mapping) for i, p in enumerate(parts))
    return body + sep + "\n".join(kept)


def sanitize_currency_symbols(text: str) -> str:
    """Chuẩn hóa ký hiệu tiền tệ USD ($) không đóng thành \\$ để tránh xung đột với LaTeX inline math delimiters."""
    return re.sub(r"(?<=\s|[~(=])(?<!\\)\$(\d+(?:\.\d+)?)(?=\s+[a-zA-Z])", r"\\$\1", text)


def sanitize_pipeline_leakages(text: str) -> str:
    """Khử sạch toàn bộ siêu dữ liệu rò rỉ từ pipeline nội bộ (Blueprint, Chặng, Notation Lock)."""
    # 1. Khử các đoạn tổng kết chặng / tóm tắt chặng do LLM tự sinh ở cuối section
    text = re.sub(
        r"(?:\n|^)[ \t]*[-—*]*[ \t]*(?:Tóm tắt (?:Chặng|Giai đoạn|Stage)\s*\d+[\.:]?|Stage\s*\d+\s*Summary[\.:]?|Tóm tắt Blueprint[\.:]?)[^\n]*(?:\n[^\n#|]+)*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # 2. Thay thế các tham chiếu Blueprint / Chặng bằng ngôn ngữ học thuật tự nhiên
    text = re.sub(r"\b(?:theo\s+)?Blueprint\s*§?[\d\.]*(?:\s*,\s*§?[\d\.]*)*\b", "the pre-registered protocol", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:trong\s+)?Blueprint\b", "the pre-registered protocol", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:Global Notation Lock(?:\s*Table)?|Bảng Ký Hiệu Toàn Cục)\b", "formal notation system", text, flags=re.IGNORECASE)
    text = re.sub(r"\bChặng\s*(\d+)\b", r"Section \1", text, flags=re.IGNORECASE)

    # 3. Sửa lỗi công thức toán LaTeX bị rò rỉ trong ô bảng: e.g., |text{Tokens} times 0.15 / 10^6 |
    text = re.sub(
        r"\|[ \t]*\\?text\{([^{}]+)\}\s*times\s*([0-9\.\^/]+)[ \t]*\|",
        r"| $\\text{\1} \\times \2$ |",
        text,
    )

    # 4. Sửa lỗi nhãn Figure lặp lại: e.g., Figure 1: Figure 1: ...
    text = re.sub(r"(Figure\s+\d+[:\.]?)\s+Figure\s+\d+[:\.]?", r"\1", text, flags=re.IGNORECASE)

    return text


def ensure_title_heading(text: str) -> str:
    """LLM đôi khi viết tiêu đề thành dòng thường (thiếu '# '); frontend/renderer chỉ nhận tiêu đề từ H1
    nên sẽ rơi về câu hỏi của người dùng. Khôi phục '# ' khi dòng đầu rõ ràng là tiêu đề front matter."""
    lines = text.lstrip().split("\n")
    first = lines[0].strip()
    if not first or first.startswith(("#", "**", "|", "```", "$$")) or len(first) > 300:
        return text
    following = next((ln.strip() for ln in lines[1:] if ln.strip()), "")
    if not re.match(r"(?:\*\*Authors:|##\s+(?:Abstract|Tóm tắt))", following, flags=re.IGNORECASE):
        return text
    return "\n".join([f"# {first.strip(chr(34))}", *lines[1:]])


def sanitize_academic_markdown(text: str) -> str:
    """Hàm tổng hợp duy nhất: chuẩn hóa toàn bộ markdown học thuật trước khi xuất/lưu trữ."""
    if not text:
        return ""

    # 0. Tiêu đề thiếu '# '
    result = ensure_title_heading(text)

    # 1. Khử rò rỉ pipeline nội bộ
    result = sanitize_pipeline_leakages(result)

    # 2. Khử placeholder tác giả
    result = sanitize_author_placeholders(result)

    # 2a. References còn là snippet thô → định dạng IEEE
    result = sanitize_raw_references(result)

    # 2a'. Gộp reference trùng tiêu đề, đánh số lại [n]
    result = dedupe_references(result)

    # 2b. '|' trong công thức của hàng bảng
    result = sanitize_table_math_pipes(result)

    # 3. Chuẩn hóa ký hiệu tiền tệ tránh xung đột inline math
    result = sanitize_currency_symbols(result)

    # 4. Chuẩn hóa tất cả các khối Mermaid
    def _mermaid_replacer(match: re.Match) -> str:
        body = match.group(1)
        sanitized_body = sanitize_mermaid_block(body)
        return f"```mermaid\n{sanitized_body}\n```"

    result = _MERMAID_BLOCK_RE.sub(_mermaid_replacer, result)

    # 5. Chuẩn hóa LaTeX math display blocks
    result = sanitize_latex_math(result)

    # 6. Chuẩn hóa Algorithm blocks
    result = sanitize_code_and_algorithm_blocks(result)

    return result.strip() + "\n"

