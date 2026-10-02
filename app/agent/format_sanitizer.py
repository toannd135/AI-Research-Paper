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

    # Thay thế ký tự xuống dòng
    s = s.replace(r"\n", "<br/>").replace("\n", "<br/>")
    # Thay thế ngoặc nhọn để tránh conflict syntax
    s = s.replace("{", "(").replace("}", ")")
    # Thay ngoặc kép bên trong thành nháy đơn
    s = s.replace('"', "'")
    # Thay toán tử || tránh xung đột nhãn cạnh
    s = s.replace("||", "‖")
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


def sanitize_academic_markdown(text: str) -> str:
    """Hàm tổng hợp duy nhất: chuẩn hóa toàn bộ markdown học thuật trước khi xuất/lưu trữ."""
    if not text:
        return ""

    # 1. Khử placeholder tác giả
    result = sanitize_author_placeholders(text)

    # 2. Chuẩn hóa tất cả các khối Mermaid
    def _mermaid_replacer(match: re.Match) -> str:
        body = match.group(1)
        sanitized_body = sanitize_mermaid_block(body)
        return f"```mermaid\n{sanitized_body}\n```"

    result = _MERMAID_BLOCK_RE.sub(_mermaid_replacer, result)

    # 3. Chuẩn hóa LaTeX math display blocks
    result = sanitize_latex_math(result)

    # 4. Chuẩn hóa Algorithm blocks
    result = sanitize_code_and_algorithm_blocks(result)

    return result.strip() + "\n"
