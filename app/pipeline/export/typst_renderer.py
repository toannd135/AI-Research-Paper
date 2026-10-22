"""Typst Academic Engine Renderer for AI Research Papers.

Converts Semantic Academic Markdown + Chart JSON specs into publication-grade,
two-column academic PDFs (IEEE / CVPR style) using Typst.

Key features:
- Single-column front matter (Title, Authors, Affiliations, Abstract, Keywords)
- True two-column body with justified typography and hyphenation
- Numbered mathematical equations with LaTeX-to-Typst math translation
- Booktabs publication tables (table.hline 1.2pt top/bottom, 0.6pt midrule, no vertical lines)
- Vector figures: Matplotlib SVG for quantitative charts, Mermaid SVG for architecture
- Clean in-text citations and canonical references section
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import typst

from app.pipeline.figures import resolve_figure_path

logger = logging.getLogger(__name__)

def _escape_typst_references(text: str) -> str:
    """Keep Markdown at-signs (e.g. Recall@10) and angle brackets (e.g. p<0.05) as literal text in Typst."""
    text = re.sub(r"(?<!\\)@", r"\\@", text)
    # '<' đứng ngay trước chữ/số mở một nhãn Typst chưa đóng: 'p<0.05' làm hỏng cả tài liệu.
    return re.sub(r"(?<!\\)<(?=\w)", r"\\<", text)


_LATEX_HINT_RE = re.compile(r"[\\=^_{]")


def _normalize_latex_math_delimiters(md: str) -> str:
    r"""LLM hay viết \[ ... \] và \( ... \) thay cho $$ ... $$ và $ ... $; đổi sang dạng bộ chuyển đổi hiểu được.

    Chỉ đổi khi nội dung giống LaTeX (có \, =, ^, _, {): '\[1\]' là trích dẫn viết thoát, không phải công thức.
    """

    def display(m: re.Match) -> str:
        return f"\n$$ {m.group(1).strip()} $$\n" if _LATEX_HINT_RE.search(m.group(1)) else m.group(0)

    def inline(m: re.Match) -> str:
        return f"${m.group(1).strip()}$" if _LATEX_HINT_RE.search(m.group(1)) else m.group(0)

    md = re.sub(r"\\\[(.+?)\\\]", display, md, flags=re.DOTALL)
    return re.sub(r"\\\((.+?)\\\)", inline, md)


def _replace_macro_braces(macro_name: str, target_name: str, s: str) -> str:
    """Replace LaTeX macros like \\underbrace{...} that may contain arbitrarily nested braces."""
    pattern = "\\" + macro_name + "{"
    while pattern in s:
        idx = s.find(pattern)
        depth = 0
        end_idx = -1
        start_brace = idx + len(pattern) - 1
        for i in range(start_brace, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        if end_idx == -1:
            break
        inner = s[start_brace + 1 : end_idx]
        s = s[:idx] + f"{target_name}({inner})" + s[end_idx + 1 :]
    return s


def _replace_latex_fractions(s: str) -> str:
    """Translate fractions using balanced groups, including nested fractions."""
    def read_group(start: int) -> tuple[str, int] | None:
        while start < len(s) and s[start].isspace():
            start += 1
        if start == len(s) or s[start] != "{":
            return None
        depth = 1
        pos = start + 1
        while pos < len(s):
            if s[pos] == "\\":
                # Escaped braces are literal delimiters, not group boundaries.
                pos += 2
                continue
            if s[pos] == "{":
                depth += 1
            elif s[pos] == "}":
                depth -= 1
                if depth == 0:
                    return s[start + 1:pos].strip(), pos + 1
            pos += 1
        return None

    parts: list[str] = []
    cursor = 0
    pattern = re.compile(r"\\(?:frac|dfrac|tfrac)(?![a-zA-Z])")
    while match := pattern.search(s, cursor):
        numerator = read_group(match.end())
        denominator = read_group(numerator[1]) if numerator else None
        if numerator is None or denominator is None:
            parts.append(s[cursor:match.end()])
            cursor = match.end()
            continue
        parts.append(s[cursor:match.start()])
        num = _replace_latex_fractions(numerator[0])
        den = _replace_latex_fractions(denominator[0])
        parts.append(f"({num}) / ({den})")
        cursor = denominator[1]
    parts.append(s[cursor:])
    return "".join(parts)


_TYPST_UPPER_SYMBOLS = {
    "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta", "Iota", "Kappa",
    "Lambda", "Xi", "Omicron", "Sigma", "Upsilon", "Phi", "Chi", "Psi", "Omega",
}


def _quote_bare_words(s: str) -> str:
    """Quote capitalised words like MSI/TME that LLMs write bare in math; Typst reads them as variables."""
    def fix(segment: str) -> str:
        def repl(m: re.Match) -> str:
            word = m.group(0)
            return word if word in _TYPST_UPPER_SYMBOLS else f'"{word}"'
        segment = re.sub(r"(?<![A-Za-z0-9_.\\])[A-Z][A-Za-z0-9]{2,}(?![A-Za-z0-9_.(])", repl, segment)
        # Hai chữ hoa khác nhau (QK, PE) cũng là biến không tồn tại; hai chữ hoa giống nhau (RR, NN, ZZ) là ký hiệu của Typst.
        return re.sub(r'(?<![A-Za-z0-9_.\\"])([A-Z])(?!\1)([A-Z])(?![A-Za-z0-9.("])', lambda m: f'"{m.group(0)}"', segment)

    parts = re.split(r'("[^"]*")', s)
    return "".join(part if part.startswith('"') else fix(part) for part in parts)


LONG_EQUATION_CHARS = 70


def _break_long_equation(math: str) -> str:
    """Ngắt dòng công thức khối quá dài ở dấu phẩy (trong ngoặc) hoặc toán tử cấp ngoài cùng.

    Typst không tự xuống dòng trong công thức, nên công thức dài tràn khỏi cột. Dòng mới chèn bằng `\\`.
    """
    if "\n" in math or len(math) <= LONG_EQUATION_CHARS:
        return math
    # Nhóm ngoặc kết thúc bằng ^top (chuyển vị) mà bị ngắt giữa chừng sẽ làm số mũ lệch dòng: chỉ ngắt ngoài ngoặc.
    max_comma_depth = 0 if re.search(r"[\])]\^(?:top|T)\s*\.?\s*$", math) else 1
    out: list[str] = []
    depth = 0
    in_quote = False
    since_break = 0
    i = 0
    while i < len(math):
        ch = math[i]
        out.append(ch)
        since_break += 1
        if ch == '"':
            in_quote = not in_quote
        elif not in_quote:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            elif since_break >= LONG_EQUATION_CHARS and i + 1 < len(math) and math[i + 1] == " ":
                nxt = math[i + 2 : i + 3]
                if (ch == "," and depth <= max_comma_depth) or (depth == 0 and ch in "+-=" and nxt != ""):
                    out.append(" \\\n")
                    since_break = 0
                    i += 1  # bỏ khoảng trắng sau điểm ngắt
        i += 1
    return "".join(out)


def latex_to_typst_math(s: str) -> str:
    """Translate LaTeX math expressions into native Typst math syntax."""
    s = s.strip()

    # 0. Clean environments & alignment
    s = re.sub(r"\\begin\{(?:aligned|split|equation\*?)\}", "", s)
    s = re.sub(r"\\end\{(?:aligned|split|equation\*?)\}", "", s)
    s = re.sub(r"\\tag\{[^}]+\}", "", s)

    # 0b. Separate adjacent backslash commands (e.g. \Delta\mathcal -> \Delta \mathcal)
    s = re.sub(r"(\\[a-zA-Z]+)(\\[a-zA-Z]+)", r"\1 \2", s)
    s = re.sub(r"\\implies(?![a-zA-Z])", " => ", s)
    s = re.sub(r"\\iff(?![a-zA-Z])", " <=> ", s)
    s = re.sub(r"\\leftrightarrow(?![a-zA-Z])", "<->", s)

    # 1. Delimiters \left and \right (Typst scales automatically)
    s = re.sub(r"\\left\s*([(\[{|.])", lambda m: "" if m.group(1) == "." else m.group(1), s)
    s = re.sub(r"\\right\s*([)\]}|.])", lambda m: "" if m.group(1) == "." else m.group(1), s)
    s = s.replace(r"\left", "").replace(r"\right", "")
    s = s.replace(r"\|", "||")
    s = s.replace(r"\parallel", "||")

    # 2. Blackboard bold & Calligraphy & Math Fonts
    s = s.replace(r"\mathbb{R}", "RR")
    s = s.replace(r"\mathbb{Z}", "ZZ")
    s = s.replace(r"\mathbb{N}", "NN")
    s = s.replace(r"\mathbb{C}", "CC")
    s = s.replace(r"\mathbb{E}", "EE")
    s = re.sub(r"\\mathbb\{([A-Za-z0-9]+)\}", r"bb(\1)", s)
    s = re.sub(r"\\mathbb\s*([0-9A-Za-z])", r"bb(\1)", s)
    s = re.sub(r"\\mathbf\{([^{}]+)\}", r"bold(\1)", s)
    s = re.sub(r"\\boldsymbol\{([^{}]+)\}", r"bold(\1)", s)
    s = re.sub(r"\\bm\{([^{}]+)\}", r"bold(\1)", s)
    s = re.sub(r"\\mathit\{([^{}]+)\}", r"italic(\1)", s)
    s = re.sub(r"\\mathrm\{([^{}]+)\}", r"upright(\1)", s)
    s = re.sub(r"\\mathtt\{([^{}]+)\}", r"mono(\1)", s)
    s = re.sub(r"\\mathcal\{([A-Za-z0-9]+)\}", r"cal(\1)", s)

    # 3. Fractions \frac{a}{b} -> (a) / (b)
    s = _replace_latex_fractions(s)

    # 4. Underbrace & Overbrace & Nested Macro Braces (using depth counter)
    s = _replace_macro_braces("underbrace", "underbrace", s)
    s = _replace_macro_braces("overbrace", "overbrace", s)
    s = _replace_macro_braces("sqrt", "sqrt", s)
    s = _replace_macro_braces("overline", "overline", s)
    s = _replace_macro_braces("underline", "underline", s)
    s = _replace_macro_braces("widehat", "hat", s)
    s = _replace_macro_braces("widetilde", "tilde", s)
    s = _replace_macro_braces("widecheck", "check", s)

    # Overset & Underset (e.g. \overset{p}{\to})
    while r"\overset" in s:
        m = re.search(r"\\overset\{([^{}]+)\}\{([^{}]+)\}", s)
        if not m:
            break
        top, base = m.group(1).strip(), m.group(2).strip()
        s = s[:m.start()] + f"limits({base})^({top})" + s[m.end():]

    while r"\underset" in s:
        m = re.search(r"\\underset\{([^{}]+)\}\{([^{}]+)\}", s)
        if not m:
            break
        bot, base = m.group(1).strip(), m.group(2).strip()
        s = s[:m.start()] + f"limits({base})_({bot})" + s[m.end():]

    # 5. Text macros: \text{...} -> "..."
    s = re.sub(r"\\text(?:bf|sf|rm|it)?\{([^}]+)\}", r'"\1"', s)
    s = re.sub(r"\\operatorname\{([^}]+)\}", r'"\1"', s)

    # 6. Multi-letter word subscripts: _{budget} -> _("budget")
    s = re.sub(r"_\{((?=(?:[0-9]*[a-zA-Z]){2})[a-zA-Z0-9]+)\}", r'_("\1")', s)
    s = re.sub(r"\^\{((?=(?:[0-9]*[a-zA-Z]){2})[a-zA-Z0-9]+)\}", r'^("\1")', s)

    # Subscripts & Superscripts with braces: _{...} -> _(...)
    for _ in range(3):
        s = re.sub(r"_\{([^{}]+)\}", r"_(\1)", s)
        s = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", s)

    # 7. Sum, Prod, Limits, Integrals
    s = re.sub(r"\\sum(?![a-zA-Z])", "sum", s)
    s = re.sub(r"\\prod(?![a-zA-Z])", "product", s)
    s = re.sub(r"\\int(?![a-zA-Z])", "integral", s)

    # 8. Operators, symbols, arrows
    s = s.replace(r"\cdot", " dot ")
    s = s.replace(r"\times", " times ")
    s = s.replace(r"\top", "top")
    s = s.replace(r"\intercal", "top")
    s = s.replace(r"\partial", "partial ")
    s = s.replace(r"\nabla", "nabla ")
    s = s.replace(r"\infty", "oo")
    s = s.replace(r"\dots", "...")
    s = s.replace(r"\cdots", "...")
    s = s.replace(r"\ldots", "...")
    s = s.replace(r"\sim", " tilde ")
    s = s.replace(r"\notin", " in.not ")
    s = re.sub(r"\\in(?![a-zA-Z])", " in ", s)
    s = s.replace(r"\subseteq", " subset.eq ").replace(r"\subset", " subset ")
    s = s.replace(r"\supseteq", " supset.eq ").replace(r"\supset", " supset ")
    s = s.replace(r"\forall", "forall ")
    s = s.replace(r"\exists", "exists ")
    s = s.replace(r"\mid", " | ")
    s = s.replace(r"\nmid", " divides.not ")
    s = s.replace(r"\$", '"$"')

    # Greek letters
    greek = [
        ("alpha", "alpha"), ("beta", "beta"), ("gamma", "gamma"), ("Gamma", "Gamma"),
        ("delta", "delta"), ("Delta", "Delta"), ("epsilon", "epsilon"), ("varepsilon", "epsilon.alt"),
        ("zeta", "zeta"), ("eta", "eta"), ("theta", "theta"), ("Theta", "Theta"),
        ("iota", "iota"), ("kappa", "kappa"), ("lambda", "lambda"), ("Lambda", "Lambda"),
        ("mu", "mu"), ("nu", "nu"), ("xi", "xi"), ("Xi", "Xi"),
        ("pi", "pi"), ("Pi", "Pi"), ("rho", "rho"), ("sigma", "sigma"), ("Sigma", "Sigma"),
        ("tau", "tau"), ("phi", "phi"), ("Phi", "Phi"), ("psi", "psi"), ("Psi", "Psi"),
        ("omega", "omega"), ("Omega", "Omega")
    ]
    for lat, typ in greek:
        s = re.sub(rf"\\{lat}(?![a-zA-Z])", typ, s)

    # Comparisons with word boundaries
    s = re.sub(r"\\(?:le|leq)(?![a-zA-Z])", "<=", s)
    s = re.sub(r"\\(?:ge|geq)(?![a-zA-Z])", ">=", s)
    s = re.sub(r"\\(?:ne|neq)(?![a-zA-Z])", "!=", s)
    s = re.sub(r"\\approx(?![a-zA-Z])", "approx", s)
    s = re.sub(r"\\(?:to|rightarrow)(?![a-zA-Z])", "->", s)
    s = re.sub(r"\\leftarrow(?![a-zA-Z])", "<-", s)
    s = re.sub(r"\\Rightarrow(?![a-zA-Z])", "=>", s)

    # Standard math functions
    s = re.sub(r"\\max(?![a-zA-Z])", "max", s)
    s = re.sub(r"\\min(?![a-zA-Z])", "min", s)
    s = re.sub(r"\\log(?![a-zA-Z])", "log", s)
    s = re.sub(r"\\ln(?![a-zA-Z])", "ln", s)
    s = re.sub(r"\\exp(?![a-zA-Z])", "exp", s)
    s = re.sub(r"\\sin(?![a-zA-Z])", "sin", s)
    s = re.sub(r"\\cos(?![a-zA-Z])", "cos", s)

    # Square root & Accents (remaining simple macros)
    s = re.sub(r"\\sqrt\[(.*?)\]\{([^{}]+)\}", r"root(\1, \2)", s)
    s = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\bar\{([^{}]+)\}", r"macron(\1)", s)
    s = re.sub(r"\\overline\{([^{}]+)\}", r"overline(\1)", s)
    s = re.sub(r"\\(?:widehat|hat)\{([^{}]+)\}", r"hat(\1)", s)
    s = re.sub(r"\\(?:widetilde|tilde)\{([^{}]+)\}", r"tilde(\1)", s)
    s = re.sub(r"\\widecheck\{([^{}]+)\}", r"check(\1)", s)

    # Vectors
    s = re.sub(r"\\vec\s*\(?([a-zA-Z0-9]+)\)?", r"arrow(\1)", s)

    # Floor & Ceil
    s = re.sub(r"\\lfloor(.*?)\\rfloor", r"floor(\1)", s)
    s = re.sub(r"\\lceil(.*?)\\rceil", r"ceil(\1)", s)

    # Spacing
    s = s.replace(r"\qquad", "  ")
    s = s.replace(r"\quad", " ")
    s = s.replace(r"\,", " ")
    s = s.replace(r"\;", " ")
    s = s.replace(r"\:", " ")
    s = s.replace(r"\ ", " ")

    # Newlines in equations: \\ -> \
    s = re.sub(r"\\\\\s*", "\\\n", s)

    # Residual LaTeX macros that Typst math does not understand
    s = re.sub(r"\\(?:[Bb]ig{1,2}[lrm]?|[Bb]iggg?[lrm]?)(?![a-zA-Z])\s*", "", s)
    s = re.sub(r"\\arg(?![a-zA-Z])", 'op("arg")', s)
    s = re.sub(r"\\(tanh|sinh|cosh|tan|sup|inf|det|dim|ker|lim|Pr)(?![a-zA-Z])", r"\1", s)
    s = re.sub(r"\\mapsto(?![a-zA-Z])", "|->", s)
    s = re.sub(r"\\ll(?![a-zA-Z])", "<<", s)
    s = re.sub(r"\\gg(?![a-zA-Z])", ">>", s)
    s = re.sub(r"\\langle(?![a-zA-Z])", "chevron.l ", s)
    s = re.sub(r"\\rangle(?![a-zA-Z])", " chevron.r", s)

    # Clean redundant spaces
    s = re.sub(r"[ \t]+", " ", s)

    # Numbers followed immediately by multi-letter variables (e.g. 2Ldk -> 2 L d k)
    def _split_vars(match: re.Match) -> str:
        num = match.group(1)
        letters = " ".join(list(match.group(2)))
        return f"{num} {letters}"
    s = re.sub(r"(\b\d+)([a-zA-Z]{2,})\b", _split_vars, s)

    s = _quote_bare_words(s.strip())
    # Math that begins with ^/_ (e.g. "mm$^2$" in prose) has no base; give it an empty one.
    if s.startswith(("^", "_")):
        s = '""' + s
    return s


def _format_table_inline(text: str) -> str:
    # Protect math with placeholders
    math_holders: list[str] = []
    def repl_m(m):
        idx = len(math_holders)
        math_holders.append(f"${latex_to_typst_math(m.group(1))}$")
        return f"TBLMATH{idx}END"
    text = re.sub(r"(?<![\\\$])\$(?!\$)([^\n$]+?)(?<![\\\$])\$(?!\$)", repl_m, text)
    text = _escape_typst_references(text)

    # Protect escaped tokens
    text = text.replace(r"\*", "\uE000").replace(r"\_", "\uE001")
    text = re.sub(r"\*\*\*([^*]+)\*\*\*", r"#strong[#emph[\1]]", text)
    text = re.sub(r"(?<!\*)\*([^* \n][^*]*?[^* \n])\*(?!\*)", r"_\1_", text)
    text = re.sub(r"(?<!\\)(?<!\*)\*(?!\*)", r"\\*", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", text)
    text = text.replace("\uE000", r"\*").replace("\uE001", r"\_")

    # Restore math
    for i, m_str in enumerate(math_holders):
        text = text.replace(f"TBLMATH{i}END", m_str)
    return text


WIDE_TABLE_COLUMNS = 4


def _figure_placement(num_cols: int) -> str:
    """Bảng từ 4 cột trở lên trải full-width trên cả hai cột để chữ không bị ép/chồng."""
    return 'placement: auto, scope: "parent", ' if num_cols >= WIDE_TABLE_COLUMNS else ""


def parse_markdown_table_to_typst(tbl_str: str, caption: str = "") -> str:
    """Convert a Markdown table into a Typst Booktabs #figure(table(...)) block."""
    lines = [l.strip() for l in tbl_str.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return ""

    def _split_row(row_str: str) -> list[str]:
        # Protect escaped pipes \|
        protected = row_str.replace(r"\|", "\uE003")
        # Protect pipes inside math $...$
        def _mask_math_pipe(m):
            return m.group(0).replace("|", "\uE004")
        protected = re.sub(r"(?<![\\\$])\$(?!\$)([^\n$]+?)(?<![\\\$])\$(?!\$)", _mask_math_pipe, protected)
        cells = [c.strip().replace("\uE004", "|").replace("\uE003", r"\|") for c in protected.strip("|").split("|")]
        return cells

    headers = _split_row(lines[0])
    num_cols = len(headers)
    if num_cols == 0:
        return ""

    data_rows = []
    for line in lines[1:]:
        if re.match(r"^\|?[-:\s|]+\|?$", line):
            continue
        cols = _split_row(line)
        while len(cols) < num_cols:
            cols.append("")
        data_rows.append(cols[:num_cols])

    def format_cell(text: str) -> str:
        return f"[{_format_table_inline(text)}]"

    # 1st column 1.3fr, others 1fr
    if num_cols > 1:
        cols_spec = "(1.3fr, " + ", ".join(["1fr"] * (num_cols - 1)) + ")"
    else:
        cols_spec = "(1fr,)"

    typ_cells = []
    for h in headers:
        clean_h = re.sub(r"^\*\*(.+)\*\*$", r"\1", h.strip())
        inner_h = _format_table_inline(clean_h)
        if inner_h.startswith("*") and inner_h.endswith("*") and len(inner_h) > 2:
            typ_cells.append(f"[{inner_h}]")
        else:
            typ_cells.append(f"[*{inner_h}*]")
    header_block = ", ".join(typ_cells)

    body_blocks = []
    for row in data_rows:
        row_cells = [format_cell(c) for c in row]
        body_blocks.append("    " + ", ".join(row_cells))
    rows_str = ",\n".join(body_blocks)

    if caption:
        cap_inner = _format_table_inline(caption)
        cap_clause = f",\n  caption: [{cap_inner}]"
    else:
        cap_clause = ""
    return f"""#figure(
  {_figure_placement(num_cols)}table(
    columns: {cols_spec},
    stroke: none,
    table.hline(stroke: 1.2pt),
    {header_block},
    table.hline(stroke: 0.6pt),
{rows_str},
    table.hline(stroke: 1.2pt),
  ){cap_clause}
)"""


def render_chart_spec_to_svg(spec: dict, out_path: Path) -> Path:
    """Use the same chart renderer for the HTML and Typst exports."""
    from app.pipeline.export.pdf_renderer import _render_chart_svg

    out_path.write_text(_render_chart_svg(spec), encoding="utf-8")
    return out_path


def render_mermaid_to_svg(code: str, out_path: Path) -> Path:
    """Render the complete original graph locally; propagate errors to the HTML fallback."""
    from app.pipeline.export.browser_renderer import mermaid_to_svg

    out_path.write_text(mermaid_to_svg(code), encoding="utf-8")
    return out_path


def markdown_to_typst(
    report_md: str,
    citations: list[dict[str, Any]] | None = None,
    work_dir: Path | None = None,
) -> str:
    """Convert Academic Markdown into a complete, standalone Typst document."""
    if work_dir is None:
        work_dir = Path(".")
    report_md = _normalize_latex_math_delimiters(report_md)

    # 1. Extract Front Matter
    title_match = re.search(r"^#\s+(.+)$", report_md, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Untitled Research Paper"

    authors = ["PaperAI Automated Research Protocol"]
    affiliations = ["Open-Source Automated Science Initiative"]
    auth_match = re.search(r"\*\*Authors:\*\*(.*?)\|\s*\*\*Affiliations:\*\*(.*?)(?=\n)", report_md)
    if auth_match:
        parsed_a = [a.strip() for a in auth_match.group(1).split(",") if a.strip()]
        parsed_aff = [a.strip() for a in auth_match.group(2).split(",") if a.strip()]
        if parsed_a:
            authors = parsed_a
        if parsed_aff:
            affiliations = parsed_aff

    abstract = ""
    keywords = []
    abs_match = re.search(r"##\s+Abstract\s*\n(.*?)(?=\n##|\Z)", report_md, re.DOTALL)
    if abs_match:
        abs_raw = abs_match.group(1).strip()
        kw_match = re.search(r"\*\*Keywords:\*\*(.+)$", abs_raw, re.MULTILINE)
        if kw_match:
            keywords = [k.strip() for k in kw_match.group(1).split(",") if k.strip()]
            abs_raw = abs_raw[:kw_match.start()].strip()
        abstract = abs_raw

    # Convert math and formatting in abstract with placeholder shielding
    abs_math_placeholders: list[str] = []
    def _repl_abs_math(m):
        idx = len(abs_math_placeholders)
        abs_math_placeholders.append(f"${latex_to_typst_math(m.group(1))}$")
        return f"ABSMATH{idx}END"
    abstract = re.sub(r"(?<![\\\$])\$(?!\$)((?:\\[$]|[^$\n])+?)(?<![\\\$])\$(?!\$)", _repl_abs_math, abstract)
    abstract = _escape_typst_references(abstract)

    abstract = abstract.replace(r"\*", "\uE000").replace(r"\_", "\uE001")
    abstract = re.sub(r"\*\*\*([^*]+)\*\*\*", r"#strong[#emph[\1]]", abstract)
    abstract = re.sub(r"___([^_\n]+?)___", r"#strong[#emph[\1]]", abstract)
    abstract = re.sub(r"\*\*([^*]+)\*\*", r"#strong[\1]", abstract)
    abstract = re.sub(r"__([^_\n]+?)__", r"#strong[\1]", abstract)
    abstract = re.sub(r"(?<!\*)\*([^* \n][^*]*?[^* \n])\*(?!\*)", r"#emph[\1]", abstract)
    abstract = re.sub(r"(?<![a-zA-Z0-9_])_([^_\n]+?)_(?![a-zA-Z0-9_])", r"#emph[\1]", abstract)
    abstract = re.sub(r"(?<!\\)\*", r"\\*", abstract)
    abstract = abstract.replace("\uE000", r"\*").replace("\uE001", r"\_")

    for i, m_str in enumerate(abs_math_placeholders):
        abstract = abstract.replace(f"ABSMATH{i}END", m_str)

    # Find where Section 1 / Body begins (Executive Summary của bản cho người đi làm đứng trước Section 1)
    sec1_match = re.search(r"\n##\s+(?:1\.|Introduction|Executive Summary)", report_md)
    body_md = report_md[sec1_match.start():] if sec1_match else report_md

    # 2. Extract block elements to placeholders
    placeholders: list[str] = []

    def save_block(content: str) -> str:
        idx = len(placeholders)
        placeholders.append(content)
        return f"\n\nTYPSTBLOCK{idx}END\n\n"

    # 2a. Chart JSON blocks
    fig_counter = [0]
    def repl_chart(m):
        fig_counter[0] += 1
        spec_str = m.group(1).strip()
        try:
            spec = json.loads(spec_str)
            svg_name = f"chart_{fig_counter[0]}.svg"
            svg_path = work_dir / svg_name
            render_chart_spec_to_svg(spec, svg_path)
            raw_caption = spec.get("caption") or spec.get("title") or f"Evaluation Metric Plot"
            clean_caption = re.sub(r"^(?:Figure|Fig\.|Biểu đồ)\s*\d+[:\.]?\s*", "", str(raw_caption).strip(), flags=re.IGNORECASE)
            clean_caption = _escape_typst_references(clean_caption)
            return save_block(f'#figure(\n  image("{svg_name}", width: 100%),\n  caption: [{clean_caption}]\n)')
        except Exception as e:
            raise ValueError(f"Không render được biểu đồ: {e}") from e
    body_md = re.sub(r"```chart[ \t]*\n(.*?)```", repl_chart, body_md, flags=re.DOTALL)

    # 2a'. Real images extracted from uploaded PDFs (path đã được postprocess gắn; chỉ nhận file trong thư mục figures)
    def repl_image(m):
        try:
            spec = json.loads(m.group(1).strip())
        except ValueError:
            logger.warning("Bỏ khối image không phải JSON")
            return ""
        src = resolve_figure_path(spec.get("path")) if isinstance(spec, dict) else None
        if src is None:
            logger.warning("Bỏ khối image không có file hợp lệ: %s", spec.get("ref") if isinstance(spec, dict) else spec)
            return ""
        fig_counter[0] += 1
        img_name = f"img_{fig_counter[0]}.png"
        shutil.copyfile(src, work_dir / img_name)
        caption = _escape_typst_references(_format_table_inline(str(spec.get("caption", ""))))
        source = _escape_typst_references(_format_table_inline(str(spec.get("source", ""))))
        source_part = f' #text(size: 0.85em, style: "italic")[Source: {source}]' if source else ""
        return save_block(
            f'#figure(\n  image("{img_name}", width: 90%),\n  caption: [{caption}{source_part}]\n)'
        )
    body_md = re.sub(r"```image[ \t]*\n(.*?)```", repl_image, body_md, flags=re.DOTALL)

    # 2b. Mermaid blocks — chú thích lấy từ dòng '**Figure N: ...**' ngay phía trên (nếu có)
    def repl_mermaid(m):
        fig_counter[0] += 1
        code = m.group(2).strip()
        svg_name = f"flow_{fig_counter[0]}.svg"
        svg_path = work_dir / svg_name
        render_mermaid_to_svg(code, svg_path)
        caption = _escape_typst_references(_format_table_inline((m.group(1) or "").strip()))
        return save_block(f'#figure(\n  image("{svg_name}", width: 100%),\n  caption: [{caption}]\n)')
    body_md = re.sub(
        r"(?:^[ \t]*\*\*(?:Figure|Fig\.|Hình)\s*\d+\s*[:.]\s*([^\n]*?)\*\*[ \t]*\n+)?```mermaid[ \t]*\n(.*?)```",
        repl_mermaid, body_md, flags=re.DOTALL | re.MULTILINE,
    )

    # JSON tables are academic tables, not code samples. Render grouped headers and row spans.
    def repl_json_table(m):
        spec = json.loads(m.group(1))
        columns = spec["columns"]
        rows = spec["rows"]
        if not columns or not rows or any(len(row) != len(columns) for row in rows):
            raise ValueError("Bảng JSON có số cột không hợp lệ")
        cells = []
        groups = spec.get("header_groups", [])
        if groups and sum(int(group["span"]) for group in groups) != len(columns):
            logger.warning("Bỏ nhóm tiêu đề bảng JSON không khớp %d cột", len(columns))
            groups = []
        if groups:
            for group in groups:
                label = _format_table_inline(str(group.get("label", "")))
                cells.append(f'table.cell(colspan: {int(group["span"])})[{label}]')
        for column in columns:
            cells.append(f'[*{_format_table_inline(str(column))}*]')
        cells.append("table.hline(stroke: 0.6pt)")
        for index, row in enumerate(rows):
            for col, value in enumerate(row):
                text = str(value) if value is not None else ""
                if col == 0 and not text.strip() and index > 0:
                    continue
                if col == 0 and text.strip():
                    span = 1
                    while index + span < len(rows) and not str(rows[index + span][0] or "").strip():
                        span += 1
                else:
                    span = 1
                cell_body = f"[{_format_table_inline(text)}]"
                if index in spec.get("bold_rows", []):
                    cell_body = f"[#strong{cell_body}]"
                cells.append(f"table.cell(rowspan: {span}){cell_body}")
        caption = _format_table_inline(str(spec.get("caption", "")))
        content = ",\n".join(cells)
        return save_block(
            f'#figure({_figure_placement(len(columns))}table(columns: {len(columns)}, stroke: none, table.hline(stroke: 1.2pt),\n'
            f'{content}, table.hline(stroke: 1.2pt)), caption: [{caption}])'
        )
    body_md = re.sub(r"```table[ \t]*\n(.*?)```", repl_json_table, body_md, flags=re.DOTALL)

    # 2c. Other Code / Algorithm blocks
    def repl_code(m):
        lang = m.group(1) or ""
        code = m.group(2).strip()
        return save_block(f"```{lang}\n{code}\n```")
    body_md = re.sub(r"```([a-zA-Z0-9_-]*)[ \t]*\n(.*?)```", repl_code, body_md, flags=re.DOTALL)

    # 2d. Display math $$ ... $$
    eq_counter = [0]
    def repl_disp_math(m):
        eq_counter[0] += 1
        math_typ = _break_long_equation(latex_to_typst_math(m.group(1)))
        return save_block(f"$ {math_typ} $ <eq:{eq_counter[0]}>")
    body_md = re.sub(r"\$\$(.+?)\$\$", repl_disp_math, body_md, flags=re.DOTALL)

    # 2e. Markdown Tables (with optional preceding Table captions)
    tbl_counter = [0]
    def repl_table(m):
        tbl_counter[0] += 1
        raw_cap = m.group(1) or "Empirical Benchmark and Comparative Evaluation"
        clean_cap = re.sub(r"^(?:Table|Bảng)\s*\d+[:\.]?\s*", "", raw_cap.strip(), flags=re.IGNORECASE).strip()
        if not clean_cap:
            clean_cap = "Empirical Benchmark and Comparative Evaluation"
        tbl_str = m.group(2).strip()
        typ_tbl = parse_markdown_table_to_typst(tbl_str, clean_cap)
        return save_block(typ_tbl)

    tbl_pattern = re.compile(
        r"(?:^[ \t]*\*\*(?:Table|Bảng)\s*\d+[:.]\s*(.*?)\*\*[ \t]*\n+)?((?:^[ \t]*\|[^\n]+\n?)+)",
        re.MULTILINE
    )
    body_md = tbl_pattern.sub(repl_table, body_md)

    # 2f. Inline math $ ... $ (shielded with placeholders to avoid formatting regex corruption)
    inline_math_placeholders: list[str] = []
    def repl_inline_math(m):
        idx = len(inline_math_placeholders)
        math_typ = latex_to_typst_math(m.group(1))
        inline_math_placeholders.append(f"${math_typ}$")
        return f"TYPSTMATH{idx}END"
    body_md = re.sub(r"(?<![\\\$])\$(?!\$)((?:\\[$]|[^$\n])+?)(?<![\\\$])\$(?!\$)", repl_inline_math, body_md)
    body_md = _escape_typst_references(body_md)

    # 3. Headings
    body_md = re.sub(r"^##\s+(.+)$", r"= \1", body_md, flags=re.MULTILINE)
    body_md = re.sub(r"^###\s+(.+)$", r"== \1", body_md, flags=re.MULTILINE)
    body_md = re.sub(r"^####\s+(.+)$", r"=== \1", body_md, flags=re.MULTILINE)

    # 4. List conversion
    # Convert * bullets to - bullets (critical for Typst bold disambiguation)
    body_md = re.sub(r"^[ \t]*\*[ \t]+", "- ", body_md, flags=re.MULTILINE)

    # 5. Bold & Italic in text
    body_md = body_md.replace(r"\*", "\uE000").replace(r"\_", "\uE001")
    body_md = re.sub(r"\*\*\*([^*\n]+?)\*\*\*", r"#strong[#emph[\1]]", body_md)
    body_md = re.sub(r"___([^_\n]+?)___", r"#strong[#emph[\1]]", body_md)
    body_md = re.sub(r"\*\*([^*\n]+?)\*\*", r"#strong[\1]", body_md)
    body_md = re.sub(r"__([^_\n]+?)__", r"#strong[\1]", body_md)
    body_md = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"#emph[\1]", body_md)
    body_md = re.sub(r"(?<![a-zA-Z0-9_])_([^_\n]+?)_(?![a-zA-Z0-9_])", r"#emph[\1]", body_md)
    # Escape any remaining dangling lone asterisks
    body_md = re.sub(r"(?<!\\)\*", r"\\*", body_md)
    body_md = body_md.replace("\uE000", r"\*").replace("\uE001", r"\_")

    # 6. Restore placeholders
    for i, b in enumerate(placeholders):
        body_md = body_md.replace(f"TYPSTBLOCK{i}END", b)

    for i, m_str in enumerate(inline_math_placeholders):
        body_md = body_md.replace(f"TYPSTMATH{i}END", m_str)

    # 7. Format authors & affiliations tuples (ensure trailing comma for 1-element arrays)
    auth_elements = [f'"{a}"' for a in authors]
    auth_str = ", ".join(auth_elements) + ("," if len(auth_elements) == 1 else "")

    affil_elements = [f'"{a}"' for a in affiliations]
    affil_str = ", ".join(affil_elements) + ("," if len(affil_elements) == 1 else "")

    kw_elements = [f'"{k}"' for k in keywords]
    kw_str = ", ".join(kw_elements) + ("," if len(kw_elements) == 1 else "")

    # Load canonical CVPR/IEEE Typst template content
    template_path = Path(__file__).parent / "templates" / "cvpr_paper.typ"
    template_code = template_path.read_text(encoding="utf-8")

    typst_doc = f"""{template_code}

#show: cvpr_paper.with(
  title: "{title}",
  authors: ({auth_str}),
  affiliations: ({affil_str}),
  abstract: [{abstract}],
  keywords: ({kw_str})
)

{body_md}
"""
    return typst_doc


_UNKNOWN_VARIABLE_RE = re.compile(r"unknown variable: (\w+)")
_MATH_SEGMENT_RE = re.compile(r"(?<!\\)\$(.*?)(?<!\\)\$", re.DOTALL)
MAX_MATH_REPAIRS = 12


def _quote_word_in_math(typst_src: str, name: str) -> str:
    """Đặt tên biến lạ (pos, softmax...) trong dấu nháy ở mọi đoạn toán $...$, bỏ qua chuỗi đã có nháy."""
    word_re = re.compile(rf'(?<![A-Za-z0-9."\\]){re.escape(name)}(?![A-Za-z0-9."])')  # '_' là chỉ số dưới, không thuộc tên

    def fix_segment(m: re.Match) -> str:
        parts = re.split(r'("[^"]*")', m.group(1))
        body = "".join(p if p.startswith('"') else word_re.sub(f'"{name}"', p) for p in parts)
        return f"${body}$"

    return _MATH_SEGMENT_RE.sub(fix_segment, typst_src)


def _compile_with_math_repair(typ_path: Path) -> bytes:
    """Biên dịch; nếu Typst báo 'unknown variable: X' (LLM viết từ trần trong công thức) thì quote X rồi thử lại.

    Hết lượt sửa hoặc không sửa được thì ném lại lỗi gốc để nơi gọi chuyển sang bộ render dự phòng.
    """
    repaired: set[str] = set()
    for _ in range(MAX_MATH_REPAIRS + 1):
        try:
            return typst.compile(typ_path)
        except typst.TypstError as exc:
            found = _UNKNOWN_VARIABLE_RE.search(str(exc))
            if not found or found.group(1) in repaired or len(repaired) >= MAX_MATH_REPAIRS:
                raise
            name = found.group(1)
            src = typ_path.read_text(encoding="utf-8")
            fixed = _quote_word_in_math(src, name)
            if fixed == src:
                raise
            repaired.add(name)
            logger.info("Typst: quote biến lạ %r trong công thức và biên dịch lại", name)
            typ_path.write_text(fixed, encoding="utf-8")
    raise RuntimeError("unreachable")


def render_report_to_pdf(
    report_md: str,
    citations: list[dict[str, Any]] | None = None,
    output_pdf_path: str | Path | None = None,
) -> bytes:
    """Compile an academic report Markdown into a publication-grade PDF via Typst."""
    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)
        typst_src = markdown_to_typst(report_md, citations=citations, work_dir=work_dir)
        typ_path = work_dir / "paper.typ"
        typ_path.write_text(typst_src, encoding="utf-8")

        pdf_bytes = _compile_with_math_repair(typ_path)

        if output_pdf_path:
            out = Path(output_pdf_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                out.write_bytes(pdf_bytes)
                logger.info(f"Generated publication PDF: {out} ({len(pdf_bytes)} bytes)")
            except PermissionError:
                import time
                fallback = out.with_stem(f"{out.stem}_{int(time.time())}")
                fallback.write_bytes(pdf_bytes)
                logger.warning(f"File {out} is locked (e.g. open in PDF viewer). Saved to {fallback} instead.")

        return pdf_bytes
