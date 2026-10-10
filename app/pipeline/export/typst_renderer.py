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

import base64
import html
import io
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

import typst

logger = logging.getLogger(__name__)

# Color palette for publication plots
_PALETTE = ["#1f4e79", "#c55a11", "#548235", "#7f6000", "#7030a0", "#2e75b6"]


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
    while r"\frac" in s:
        m = re.search(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", s)
        if not m:
            break
        num, den = m.group(1).strip(), m.group(2).strip()
        s = s[:m.start()] + f"({num}) / ({den})" + s[m.end():]

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
    s = re.sub(r"_\{([a-zA-Z]{2,})\}", r'_("\1")', s)
    s = re.sub(r"\^\{([a-zA-Z]{2,})\}", r'^("\1")', s)

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

    # Clean redundant spaces
    s = re.sub(r"[ \t]+", " ", s)

    # Numbers followed immediately by multi-letter variables (e.g. 2Ldk -> 2 L d k)
    def _split_vars(match: re.Match) -> str:
        num = match.group(1)
        letters = " ".join(list(match.group(2)))
        return f"{num} {letters}"
    s = re.sub(r"(\b\d+)([a-zA-Z]{2,})\b", _split_vars, s)

    return s.strip()


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

    def _format_inner(text: str) -> str:
        # Protect math with placeholders
        math_holders: list[str] = []
        def repl_m(m):
            idx = len(math_holders)
            math_holders.append(f"${latex_to_typst_math(m.group(1))}$")
            return f"TBLMATH{idx}END"
        text = re.sub(r"(?<![\\\$])\$(?!\$)([^\n$]+?)(?<![\\\$])\$(?!\$)", repl_m, text)

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

    def format_cell(text: str) -> str:
        return f"[{_format_inner(text)}]"

    # 1st column 1.3fr, others 1fr
    if num_cols > 1:
        cols_spec = "(1.3fr, " + ", ".join(["1fr"] * (num_cols - 1)) + ")"
    else:
        cols_spec = "(1fr,)"

    typ_cells = []
    for h in headers:
        clean_h = re.sub(r"^\*\*(.+)\*\*$", r"\1", h.strip())
        inner_h = _format_inner(clean_h)
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
        cap_inner = _format_inner(caption)
        cap_clause = f",\n  caption: [{cap_inner}]"
    else:
        cap_clause = ""
    return f"""#figure(
  table(
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
    """Render a quantitative chart specification (bar, line, barh) into an SVG file."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [str(x) for x in spec["labels"]]
    series = [s for s in spec["series"] if len(s.get("values", [])) == len(labels)]
    if not labels or not series:
        raise ValueError("Chart spec lacks valid labels or series")

    kind = spec.get("type", "bar")
    plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 8.5, "svg.fonttype": "path"})
    fig, ax = plt.subplots(figsize=(4.8, 2.8))
    n = len(series)

    if kind == "line":
        for i, s in enumerate(series):
            ax.plot(labels, s["values"], marker="o", linewidth=1.6, color=_PALETTE[i % len(_PALETTE)], label=s.get("name"))
    else:
        width = 0.8 / n
        positions = range(len(labels))
        for i, s in enumerate(series):
            offset = [p - 0.4 + width * (i + 0.5) for p in positions]
            color = _PALETTE[i % len(_PALETTE)]
            if kind == "barh":
                bars = ax.barh(offset, s["values"], height=width, color=color, label=s.get("name"))
            else:
                bars = ax.bar(offset, s["values"], width=width, color=color, label=s.get("name"))
            ax.bar_label(bars, fmt="%g", fontsize=6.5, padding=2)

        if kind == "barh":
            ax.set_yticks(list(positions), labels)
            ax.invert_yaxis()
        else:
            ax.set_xticks(list(positions), labels, rotation=20 if max(map(len, labels)) > 10 else 0, ha="right" if max(map(len, labels)) > 10 else "center")

    if spec.get("x_label"):
        ax.set_xlabel(spec["x_label"], fontsize=8)
    if spec.get("y_label"):
        ax.set_ylabel(spec["y_label"], fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x" if kind == "barh" else "y", linestyle=":", alpha=0.6)
    if n > 1 or series[0].get("name"):
        ax.legend(frameon=False, fontsize=7.5)

    fig.tight_layout()
    fig.savefig(str(out_path), format="svg", bbox_inches="tight")
    plt.close(fig)
    return out_path


def _render_offline_flowchart(code: str, out_path: Path) -> Path:
    """Render a clean offline vector flowchart using matplotlib when network rendering is unavailable."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    subgraphs = re.findall(r'subgraph\s+[A-Za-z0-9_]+\s*\["([^"]+)"\]', code)
    nodes = re.findall(r'[A-Za-z0-9_]+\["([^"]+)"\]', code)

    stages = [sg.replace("<br/>", "\n") for sg in subgraphs]
    if not stages:
        node_labels = [n.replace("<br/>", "\n") for n in nodes][:4]
        stages = node_labels or ["Experimental Setup", "Execution & Inference", "Statistical Analysis", "Reporting & Verification"]

    n_stages = max(len(stages), 1)
    fig, ax = plt.subplots(figsize=(6.5, 2.2), dpi=200)
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3)

    box_w = min(2.0, 7.5 / n_stages)
    box_h = 1.4
    spacing = (8.5 - (n_stages * box_w)) / max(n_stages - 1, 1)

    for i, stage_name in enumerate(stages):
        x = 0.5 + i * (box_w + spacing)
        y = 0.8
        p = FancyBboxPatch(
            (x, y), box_w, box_h,
            boxstyle="round,pad=0.08,rounding_size=0.12",
            facecolor="#f8fafc",
            edgecolor=_PALETTE[i % len(_PALETTE)],
            linewidth=1.4,
        )
        ax.add_patch(p)
        clean_text = stage_name.replace("  ", " ").strip()
        ax.text(
            x + box_w / 2, y + box_h / 2,
            clean_text,
            ha="center", va="center",
            fontsize=7, fontweight="bold",
            color="#1e293b",
        )

        if i < n_stages - 1:
            ax.annotate(
                "",
                xy=(x + box_w + spacing, y + box_h / 2),
                xytext=(x + box_w, y + box_h / 2),
                arrowprops=dict(arrowstyle="->", color="#64748b", lw=1.4),
            )

    fig.tight_layout()
    fig.savefig(str(out_path), format="svg", bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_mermaid_to_svg(code: str, out_path: Path) -> Path | None:
    """Render Mermaid syntax to SVG via mermaid.ink with graceful offline fallback."""
    import httpx
    try:
        enc = base64.b64encode(code.encode("utf-8")).decode("ascii")
        url = f"https://mermaid.ink/svg/{enc}"
        r = httpx.get(url, timeout=5)
        if r.status_code == 200 and "<svg" in r.text:
            out_path.write_text(r.text, encoding="utf-8")
            return out_path
    except Exception as e:
        logger.info(f"Online Mermaid rendering unavailable ({e}). Using offline vector flowchart generator.")

    try:
        return _render_offline_flowchart(code, out_path)
    except Exception as e:
        logger.warning(f"Offline flowchart rendering failed: {e}")
        return None


def markdown_to_typst(
    report_md: str,
    citations: list[dict[str, Any]] | None = None,
    work_dir: Path | None = None,
) -> str:
    """Convert Academic Markdown into a complete, standalone Typst document."""
    if work_dir is None:
        work_dir = Path(".")

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

    # Find where Section 1 / Body begins
    sec1_match = re.search(r"\n##\s+(?:1\.|Introduction)", report_md)
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
            return save_block(f'#figure(\n  image("{svg_name}", width: 100%),\n  caption: [{clean_caption}]\n)')
        except Exception as e:
            logger.warning(f"Failed to render chart spec: {e}")
            return ""
    body_md = re.sub(r"```chart[ \t]*\n(.*?)```", repl_chart, body_md, flags=re.DOTALL)

    # 2b. Mermaid blocks
    def repl_mermaid(m):
        fig_counter[0] += 1
        code = m.group(1).strip()
        svg_name = f"flow_{fig_counter[0]}.svg"
        svg_path = work_dir / svg_name
        res = render_mermaid_to_svg(code, svg_path)
        if res:
            return save_block(f'#figure(\n  image("{svg_name}", width: 100%),\n  caption: [System Architectural and Evaluation Pipeline Overview.]\n)')
        return ""
    body_md = re.sub(r"```mermaid[ \t]*\n(.*?)```", repl_mermaid, body_md, flags=re.DOTALL)

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
        math_typ = latex_to_typst_math(m.group(1))
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

        pdf_bytes = typst.compile(typ_path)

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
