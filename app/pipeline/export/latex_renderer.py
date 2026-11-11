"""Report Markdown → gói LaTeX IEEEtran (paper.tex + references.bib + figures/*.pdf).

- Trích dẫn [n] → \\cite{refn}; mục '## References' thay bằng \\bibliography{references}.
- Khối ```chart → figures/chart_k.pdf (vector, font nhúng) hoặc .eps; khối ```image → PNG gốc.
- Khối ```table / bảng Markdown → booktabs (table* khi từ 4 cột).
- Sơ đồ ```mermaid không có bộ chuyển PDF thuần Python: lưu mã nguồn .mmd và chèn khung chỗ trống để xuất tay.
"""

import io
import json
import logging
import os
import re
import shutil
import zipfile
from pathlib import Path

from app.pipeline.export.bibliography import (
    cite_key,
    parse_references,
    references_to_bibtex,
    split_references,
    survey_table_spec,
)

logger = logging.getLogger(__name__)

_TEX_ESCAPES = str.maketrans({
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
})
_UNICODE = {
    "±": r"$\pm$", "×": r"$\times$", "≥": r"$\geq$", "≤": r"$\leq$", "≈": r"$\approx$", "→": r"$\rightarrow$",
    "α": r"$\alpha$", "β": r"$\beta$", "γ": r"$\gamma$", "δ": r"$\delta$", "ε": r"$\epsilon$", "λ": r"$\lambda$",
    "μ": r"$\mu$", "σ": r"$\sigma$", "τ": r"$\tau$", "φ": r"$\phi$", "ω": r"$\omega$", "Δ": r"$\Delta$",
    "−": "-", "\u00a0": "~", "\u2009": r"\,", "“": "``", "”": "''", "’": "'", "…": r"\ldots{}",
}
_MATH_RE = re.compile(r"(?<![\\$])\$(?!\$)((?:\\[$]|[^$\n])+?)(?<![\\$])\$(?!\$)|\\\((.+?)\\\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_CITE_RE = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")
_NUMBERING_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+")
_CAPTION_PREFIX_RE = re.compile(r"^(?:Table|Bảng|Figure|Fig\.|Hình|Biểu đồ)\s*\d+\s*[:.]\s*", re.IGNORECASE)
# pdflatex dùng inputenc/fontenc; XeTeX (Tectonic) dùng font OpenType Times để đủ ký tự Unicode (·, —, é...)
# newtxmath (nạp TRƯỚC fontspec[no-math]): công thức cùng nét Times với thân bài, không còn Computer Modern; đã gồm ký hiệu AMS
_COMMON_PACKAGES = r"""\usepackage{iftex}
\usepackage{amsmath}
\usepackage{newtxmath}
\ifPDFTeX
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\else
\usepackage[no-math]{fontspec}
\setmainfont{texgyretermes}[Extension=.otf,UprightFont=*-regular,BoldFont=*-bold,ItalicFont=*-italic,BoldItalicFont=*-bolditalic]
\fi
\usepackage{graphicx,booktabs,multirow,textcomp,xcolor,array,tabularx}
\setlength{\textfloatsep}{8pt plus 2pt minus 2pt}
\setlength{\dbltextfloatsep}{8pt plus 2pt minus 2pt}
\renewcommand{\topfraction}{0.9}
\renewcommand{\dbltopfraction}{0.9}
\renewcommand{\textfraction}{0.07}
\renewcommand{\floatpagefraction}{0.8}
\renewcommand{\dblfloatpagefraction}{0.8}
\setcounter{topnumber}{3}
\setcounter{dbltopnumber}{3}
\setcounter{totalnumber}{5}
"""
_PREAMBLES = {
    "ieee": "\\documentclass[conference]{IEEEtran}\n" + _COMMON_PACKAGES + "\\usepackage{cite}\n\\usepackage[hidelinks]{hyperref}\n",
    # cvpr.sty (+ ieeenat_fullname.bst / ieee_fullname.bst) do hội nghị cung cấp, đặt cạnh paper.tex
    "cvpr": "\\documentclass[10pt,twocolumn,letterpaper]{article}\n\\usepackage[review]{cvpr}\n" + _COMMON_PACKAGES
    + "\\usepackage[pagebackref,breaklinks,colorlinks]{hyperref}\n",
}
_APPENDIX_RE = re.compile(r"^Appendix\s+[A-Z]\.?\s*", re.IGNORECASE)


def _expand_cites(spec: str) -> str:
    keys: list[int] = []
    for part in re.split(r"\s*,\s*", spec):
        m = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", part)
        if m and int(m.group(1)) <= int(m.group(2)) <= int(m.group(1)) + 50:
            keys += range(int(m.group(1)), int(m.group(2)) + 1)
        else:
            keys += [int(n) for n in re.findall(r"\d+", part)]
    return r"\cite{" + ",".join(cite_key(k) for k in dict.fromkeys(keys)) + "}"


def inline_to_tex(text: str) -> str:
    """Markdown inline → LaTeX: giữ công thức, escape ký tự đặc biệt, **đậm**, *nghiêng*, `code`, link, [n]."""
    holders: list[str] = []

    def hold(tex: str) -> str:
        holders.append(tex)
        return f"PAIHOLD{len(holders) - 1}END"

    text = _MATH_RE.sub(lambda m: hold("$" + (m.group(1) or m.group(2)) + "$"), text)
    text = _LINK_RE.sub(lambda m: hold(
        r"\href{" + m.group(2).replace("%", r"\%").replace("#", r"\#") + "}{" + inline_to_tex(m.group(1)) + "}"), text)
    text = text.replace(r"\*", "PAISTAR").replace(r"\_", "PAIUNDER")
    text = re.sub(r'"([^"\n]+?)"', r"``\1''", text)  # nháy thẳng → nháy mở/đóng kiểu TeX (không thì in ra ” ở cả hai đầu)
    text = text.translate(_TEX_ESCAPES)
    for ch, tex in _UNICODE.items():
        text = text.replace(ch, tex)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\\textbf{\\emph{\1}}", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"\\emph{\1}", text)
    text = re.sub(r"`([^`\n]+?)`", r"\\texttt{\1}", text)
    text = _CITE_RE.sub(lambda m: _expand_cites(m.group(1)), text)
    text = text.replace("PAISTAR", r"\*").replace("PAIUNDER", r"\_")
    for i, tex in enumerate(holders):
        text = text.replace(f"PAIHOLD{i}END", tex)
    return text


CAPTION_MAX_CITES = 3  # caption liệt kê nhiều trích dẫn hơn → bỏ cụm đó (trích dẫn nằm ở thân bài/bảng)
_CITE_RUN_RE = re.compile(r"\s*(?:\[\d+(?:\s*[,–-]\s*\d+)*\](?:\s*,\s*(?=\[))?)+")


def _trim_caption_cites(raw: str) -> str:
    """Bỏ cụm trích dẫn dài (≥4 nguồn, vd. '[32], [28], [30], [12]' hay '[2, 37, 42, 5]') khỏi caption để caption ngắn."""
    def _drop(m: re.Match) -> str:
        return "" if len(re.findall(r"\d+", m.group(0))) > CAPTION_MAX_CITES else m.group(0)

    text = _CITE_RUN_RE.sub(_drop, raw)
    return re.sub(r"\s+([.,;:)])", r"\1", re.sub(r"\(\s*\)", "", text)).strip()


def _clean_caption(raw: str) -> str:
    return inline_to_tex(_trim_caption_cites(_CAPTION_PREFIX_RE.sub("", raw.strip())))


_ROMAN = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
_TABLE_REF_RE = re.compile(r"\b(Tables?)(\s+)(\d+)((?:\s*(?:,|and|&|–|-|to)\s*\d+)*)\b")
_SOURCE_TABLE_RE = re.compile(r"\s+(?:of|in|from)\s+(?:\[\d+\]|the\s+original\b)")


def _roman(n: int) -> str:
    out = ""
    for value, sym in _ROMAN:
        while n >= value:
            out, n = out + sym, n - value
    return out


def roman_table_refs(text: str) -> str:
    """Kiểu IEEE: bảng đánh số La Mã nên 'Table 3' trong thân bài → 'Table III'.

    Giữ nguyên dòng caption '**Table N: …**' và tham chiếu tới bảng của bài khác ('Table 2 of [5]', '[52, Table 1]')."""
    def _sub(m: re.Match) -> str:
        line_start = text.rfind("\n", 0, m.start()) + 1
        caption_line = re.fullmatch(r"\s*\*\*", text[line_start:m.start()]) and text[m.end():m.end() + 1] in ":."
        if caption_line or _SOURCE_TABLE_RE.match(text, m.end()) or re.search(r"\[[\d,\s]*,\s*$", text[max(0, m.start() - 40):m.start()]):
            return m.group(0)  # dòng caption '**Table N:' do bộ đọc bảng xử lý; bảng của bài khác giữ số gốc
        nums = re.sub(r"\d+", lambda d: _roman(int(d.group(0))), m.group(3) + m.group(4))
        return f"{m.group(1)}{m.group(2)}{nums}"

    return _TABLE_REF_RE.sub(_sub, text)


def taxonomy_figure(root: str, branches: list[tuple[str, list[str]]], caption: str) -> str:
    """Taxonomy dạng hình native LaTeX: gốc ở trên, mỗi trục một cột, lá liệt kê dưới trục (chữ Times, cỡ chú thích).

    Thay cho cây Mermaid nhiều nút bị thu nhỏ tới mức không đọc được khi in."""
    n = len(branches)
    depth = max(len(leaves) for _, leaves in branches)
    head = " & ".join(rf"\textbf{{{inline_to_tex(b)}}}" for b, _ in branches) + r" \\"
    rows = [
        " & ".join(inline_to_tex(leaves[k]) if k < len(leaves) else "" for _, leaves in branches) + r" \\[1pt]"
        for k in range(depth)
    ]
    env = "figure*" if n > 3 else "figure"
    width = r"\textwidth" if n > 3 else r"\columnwidth"
    return (
        f"\\begin{{{env}}}[!t]\n\\centering\n\\footnotesize\n"
        f"\\fbox{{\\textbf{{{inline_to_tex(root)}}}}}\\\\[4pt]\n"
        "\\setlength{\\tabcolsep}{3pt}\n"
        f"\\begin{{tabularx}}{{{width}}}{{@{{}}*{{{n}}}{{>{{\\centering\\arraybackslash}}X}}@{{}}}}\n\\toprule\n{head}\n\\midrule\n"
        + "\n".join(rows)
        + f"\n\\bottomrule\n\\end{{tabularx}}\n\\caption{{{_clean_caption(caption)}}}\n\\end{{{env}}}"
    )


_SHORT_CELL = 14  # cột có mọi ô ngắn hơn ngưỡng này không cần xuống dòng
_PAGE_LINES = 58  # số dòng chữ nhỏ vừa một trang, dùng để cắt bảng dài thành nhiều phần "(continued)"


def _plain(text) -> str:
    return re.sub(r"\*\*|\*|`|\$", "", "" if text is None else str(text)).strip()


def _column_specs(columns: list[str], rows: list[list]) -> list[str]:
    """Cột số → c; cột chữ ngắn → l; cột chữ dài → X (tự xuống dòng, căn trái) để bảng không tràn lề."""
    specs = []
    for j, head in enumerate(columns):
        cells = [_plain(r[j]) for r in rows]
        numeric = sum(bool(re.fullmatch(r"[-+–−]?[\d.,%±+\-–− ]+[a-zA-Z%]{0,2}", c)) for c in cells if c)
        longest = max([len(_plain(head))] + [len(c) for c in cells])
        if cells and numeric >= max(1, len([c for c in cells if c]) / 2) and longest <= _SHORT_CELL:
            specs.append("c")
        elif longest <= _SHORT_CELL:
            specs.append("l")
        else:
            specs.append(r">{\raggedright\arraybackslash}X")
    return specs


def _is_wide(columns: list[str], rows: list[list]) -> bool:
    longest = [max([len(_plain(c))] + [len(_plain(r[j])) for r in rows]) for j, c in enumerate(columns)]
    return len(columns) >= 4 or sum(min(n, 40) for n in longest) > 55


def _row_lines(row: list, specs: list[str], wide: bool) -> int:
    """Ước lượng số dòng một hàng chiếm sau khi xuống dòng trong các cột X."""
    flexible = [j for j, s in enumerate(specs) if "X" in s]
    if not flexible:
        return 1
    fixed = sum(max(4, len(_plain(row[j]))) for j in range(len(specs)) if j not in flexible)
    per_col = max(8, ((150 if wide else 62) - fixed) // len(flexible))
    return max(-(-len(_plain(row[j])) // per_col) for j in flexible)


def _tabular(columns: list[str], rows: list[list], groups=None, bold_rows=(), wide: bool = False, first_row: int = 0) -> str:
    """Bảng booktabs; ô cột đầu rỗng = gộp dọc (multirow); header_groups = multicolumn."""
    n = len(columns)
    specs = _column_specs(columns, rows)
    size = r"\scriptsize" if n >= 7 else r"\footnotesize"
    width = r"\textwidth" if wide else r"\columnwidth"
    flexible = any("X" in s for s in specs)
    begin = (rf"\begin{{tabularx}}{{{width}}}{{@{{}}{''.join(specs)}@{{}}}}" if flexible
             else rf"\begin{{tabular}}{{@{{}}{''.join(specs)}@{{}}}}")
    lines = [size, r"\setlength{\tabcolsep}{4pt}", begin, r"\toprule"]
    if groups and sum(int(g["span"]) for g in groups) == n:
        cells = [rf"\multicolumn{{{int(g['span'])}}}{{c}}{{{inline_to_tex(str(g.get('label', '')))}}}" for g in groups]
        lines.append(" & ".join(cells) + r" \\")
    lines.append(" & ".join(rf"\textbf{{{inline_to_tex(c)}}}" for c in columns) + r" \\")
    lines.append(r"\midrule")
    grouped = any(not str(r[0] or "").strip() for r in rows[1:])
    for i, row in enumerate(rows):
        if grouped and i > 0 and str(row[0] or "").strip():
            lines.append(r"\midrule[0.3pt]")  # bảng có ô gộp dọc: kẻ mảnh giữa các nhóm cho dễ dò hàng
        cells = []
        for j, v in enumerate(row):
            text = "" if v is None else str(v)
            if j == 0 and not text.strip() and i > 0:
                cells.append("")
                continue
            body = inline_to_tex(text)
            if first_row + i in bold_rows:
                body = rf"\textbf{{{body}}}"
            if j == 0 and text.strip():
                span = 1
                while i + span < len(rows) and not str(rows[i + span][0] or "").strip():
                    span += 1
                if span > 1:
                    body = rf"\multirow{{{span}}}{{*}}{{{body}}}"
            cells.append(body)
        lines.append(" & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabularx}" if flexible else r"\end{tabular}"]
    return "\n".join(lines)


def _table_env(columns, rows, caption: str, groups=None, bold_rows=()) -> str:
    """Bảng nổi (float) kiểu LaTeX; bảng dài hơn một trang được cắt thành nhiều phần '(continued)' (float không tự ngắt trang)."""
    wide = _is_wide(columns, rows)
    env = "table*" if wide else "table"
    specs = _column_specs(columns, rows)
    chunks: list[tuple[int, list[list]]] = []
    start, used = 0, 0
    for i, row in enumerate(rows):
        lines = _row_lines(row, specs, wide)
        # chỉ cắt tại hàng bắt đầu nhóm mới, không cắt giữa ô gộp dọc
        if used + lines > _PAGE_LINES and i > start and str(row[0] or "").strip():
            chunks.append((start, rows[start:i]))
            start, used = i, 0
        used += lines
    chunks.append((start, rows[start:]))
    cap = _clean_caption(caption)
    parts = []
    for k, (first, part) in enumerate(chunks):
        label = cap if k == 0 else rf"{cap} (continued)"
        prefix = r"\addtocounter{table}{-1}" + "\n" if k else ""
        tab = _tabular(columns, part, groups, bold_rows, wide, first)
        parts.append(f"{prefix}\\begin{{{env}}}[!t]\n\\centering\n\\caption{{{label}}}\n{tab}\n\\end{{{env}}}")
    return "\n\n".join(parts)


def _split_md_row(line: str) -> list[str]:
    protected = line.strip().replace(r"\|", "PAIPIPE")
    protected = _MATH_RE.sub(lambda m: m.group(0).replace("|", "PAIMPIPE"), protected)
    return [c.strip().replace("PAIMPIPE", "|").replace("PAIPIPE", "|") for c in protected.strip("|").split("|")]


def _md_table(lines: list[str], caption: str) -> str:
    rows = [r for r in lines if not re.match(r"^\|?[-:\s|]+\|?$", r.strip())]
    header, body = _split_md_row(rows[0]), [_split_md_row(r) for r in rows[1:]]
    n = len(header)
    body = [(r + [""] * n)[:n] for r in body]
    header = [re.sub(r"^\*\*(.+)\*\*$", r"\1", h) for h in header]
    return _table_env(header, body, caption or "Comparative evaluation")


_COLUMN_PT, _TEXT_PT = 252.0, 516.0  # bề rộng cột / cả trang của IEEEtran (pt)
_DIAGRAM_FONT_RATIO = 0.62  # chữ Mermaid 16px = 12pt → ~7.5pt, ngang chữ chú thích


def _diagram_scale(pdf: bytes, wide: bool) -> float:
    """Tỉ lệ bề rộng sơ đồ so với cột/trang để chữ trong sơ đồ không to hơn chữ thân bài."""
    import pymupdf

    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        natural = doc[0].rect.width
    return round(min(1.0, natural * _DIAGRAM_FONT_RATIO / (_TEXT_PT if wide else _COLUMN_PT)), 3)


def report_to_latex(
    report_md: str, work_dir: Path, chart_format: str = "pdf", add_survey_table: bool = False, template: str = "ieee",
    render_diagrams: bool = False,
) -> str:
    """Trả về nội dung paper.tex (template: ieee | cvpr); ghi figures/ vào work_dir."""
    if template not in _PREAMBLES:
        raise ValueError(f"Template LaTeX không hỗ trợ: {template}")
    from app.pipeline.export.figure_layout import WIDE, chart_span, compact_tree, mermaid_span, two_level_tree
    from app.pipeline.export.pdf_renderer import _render_chart_svg
    from app.pipeline.figures import resolve_figure_path

    fig_dir = work_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    body_md, _ = split_references(report_md)
    refs = parse_references(report_md)

    title_m = re.search(r"^#\s+(.+)$", body_md, re.MULTILINE)
    title = inline_to_tex(title_m.group(1).strip()) if title_m else "Untitled Research Paper"
    authors, affs = [], []
    am = re.search(r"\*\*Authors:\*\*(.*?)(?:\|\s*|\s*\n\s*)\*\*Affiliations:\*\*(.*?)(?=\n)", body_md)
    if am:
        # tên giữ chỗ của pipeline không phải tác giả thật → bỏ (khớp typst_renderer)
        placeholders = {"PaperAI Automated Research Protocol", "Open-Source Automated Science Initiative"}
        authors = [a.strip() for a in am.group(1).split(",") if a.strip() and a.strip() not in placeholders]
        affs = [a.strip() for a in am.group(2).split(",") if a.strip() and a.strip() not in placeholders]
    if not authors:
        authors, affs = _system_author()
    abstract, keywords = "", []
    abs_m = re.search(r"##\s+Abstract\s*\n(.*?)(?=\n##|\Z)", body_md, re.DOTALL)
    if abs_m:
        abstract = abs_m.group(1).strip()
        kw = re.search(r"\*\*Keywords:\*\*(.+)$", abstract, re.MULTILINE)
        if kw:
            keywords = [k.strip() for k in kw.group(1).split(",") if k.strip()]
            abstract = abstract[: kw.start()].strip()
    sec1 = re.search(r"\n##\s+(?:1\.|Introduction|Executive Summary)", body_md)
    body = body_md[sec1.start():] if sec1 else body_md
    if add_survey_table and (spec := survey_table_spec(refs)):
        body += "\n\n```table\n" + json.dumps(spec, ensure_ascii=False) + "\n```\n"

    blocks: list[str] = []
    counter = [0]

    def keep(tex: str) -> str:
        blocks.append(tex)
        return f"\n\nPAIBLOCK{len(blocks) - 1}END\n\n"

    def figure(file: str, caption: str, wide: bool = False, scale: float = 1.0) -> str:
        env = "figure*" if wide else "figure"
        width = (r"\textwidth" if wide else r"\columnwidth") if scale == 1.0 else (
            f"{scale}\\textwidth" if wide else f"{scale}\\columnwidth")
        # giới hạn chiều cao để sơ đồ dọc rất cao không tràn trang
        return (f"\\begin{{{env}}}[!t]\n\\centering\n"
                f"\\includegraphics[width={width},height=0.42\\textheight,keepaspectratio]{{{file}}}\n"
                f"\\caption{{{_clean_caption(caption)}}}\n\\end{{{env}}}")

    def repl_chart(m):
        counter[0] += 1
        spec = json.loads(m.group(1))
        name = f"chart_{counter[0]}"
        data = _render_chart_svg(spec, chart_format)
        (fig_dir / f"{name}.{chart_format}").write_bytes(data)
        caption = str(spec.get("caption") or spec.get("title") or "Evaluation results")
        return keep(figure(f"figures/{name}", caption, chart_span(spec) == WIDE))

    def repl_image(m):
        try:
            spec = json.loads(m.group(1))
        except ValueError:
            return ""
        src = resolve_figure_path(spec.get("path")) if isinstance(spec, dict) else None
        if src is None:
            return ""
        counter[0] += 1
        name = f"img_{counter[0]}.png"
        shutil.copyfile(src, fig_dir / name)
        return keep(figure(f"figures/{name}", str(spec.get("caption", "")), spec.get("layout") == WIDE, 0.9))

    def repl_mermaid(m):
        counter[0] += 1
        name = f"flow_{counter[0]}"
        title, extra = (m.group(1) or "").strip(), (m.group(2) or "").strip()
        cap = (title + (" " + extra if extra else "")) or "System diagram"
        tree = two_level_tree(m.group(3).strip())
        if tree and sum(len(leaves) for _, leaves in tree[1]) >= TAXONOMY_MIN_LEAVES:
            return keep(taxonomy_figure(tree[0], tree[1], cap))
        code = compact_tree(m.group(3).strip())
        (fig_dir / f"{name}.mmd").write_text(code + "\n", encoding="utf-8")
        if render_diagrams:
            from app.pipeline.export.browser_renderer import mermaid_to_pdf

            try:
                data = mermaid_to_pdf(code)
                (fig_dir / f"{name}.pdf").write_bytes(data)
                wide = mermaid_span(code) == WIDE
                return keep(figure(f"figures/{name}", cap, wide, _diagram_scale(data, wide)))
            except Exception:  # thiếu Chromium/Mermaid: giữ mã .mmd và khung giữ chỗ
                logger.exception("Không render được sơ đồ %s sang PDF", name)
        placeholder = inline_to_tex(f"Diagram: export figures/{name}.mmd to PDF and replace this box with an includegraphics.")
        return keep("\\begin{figure}[!t]\n\\centering\n"
                    f"\\fbox{{\\parbox{{0.9\\columnwidth}}{{\\centering {placeholder}}}}}\n"
                    f"\\caption{{{_clean_caption(cap)}}}\n\\end{{figure}}")

    def repl_json_table(m):
        spec = json.loads(m.group(1))
        cols, rows = [str(c) for c in spec["columns"]], spec["rows"]
        if not cols or not rows or any(len(r) != len(cols) for r in rows):
            raise ValueError("Bảng JSON có số cột không hợp lệ")
        return keep(_table_env(cols, rows, str(spec.get("caption", "")), spec.get("header_groups"), set(spec.get("bold_rows", []))))

    def repl_code(m):
        return keep("\\begin{footnotesize}\n\\begin{verbatim}\n" + m.group(2).strip() + "\n\\end{verbatim}\n\\end{footnotesize}")

    body = re.sub(r"```chart[ \t]*\n(.*?)```", repl_chart, body, flags=re.DOTALL)
    body = re.sub(r"```image[ \t]*\n(.*?)```", repl_image, body, flags=re.DOTALL)
    body = re.sub(r"(?:^[ \t]*\*\*(?:Figure|Fig\.|Hình)\s*\d+\s*[:.]\s*([^\n]*?)\*\*([^\n]*)\n+)?```mermaid[ \t]*\n(.*?)```",
                  repl_mermaid, body, flags=re.DOTALL | re.MULTILINE)
    body = re.sub(r"```table[ \t]*\n(.*?)```", repl_json_table, body, flags=re.DOTALL)
    body = re.sub(r"```([a-zA-Z0-9_-]*)[ \t]*\n(.*?)```", repl_code, body, flags=re.DOTALL)
    body = re.sub(r"\$\$(.+?)\$\$", lambda m: keep("\\begin{equation}\n" + m.group(1).strip() + "\n\\end{equation}"), body, flags=re.DOTALL)
    if template == "ieee":
        body = roman_table_refs(body)

    out: list[str] = []
    lines = body.splitlines()
    i, para = 0, []
    in_appendix = False

    def flush():
        if para:
            out.append(inline_to_tex(" ".join(para)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush()
        elif (h := re.match(r"^(#{2,4})\s+(.+)$", stripped)):
            flush()
            cmd = {2: "section", 3: "subsection", 4: "subsubsection"}[len(h.group(1))]
            raw_heading = h.group(2).strip()
            if cmd == "section" and _APPENDIX_RE.match(raw_heading):
                if not in_appendix:
                    out.append("\\appendix")
                    in_appendix = True
                raw_heading = _APPENDIX_RE.sub("", raw_heading)
            heading = inline_to_tex(_NUMBERING_RE.sub("", raw_heading))
            out.append(f"\\{cmd}{{{heading}}}")
        elif (b := re.fullmatch(r"PAIBLOCK(\d+)END", stripped)):
            flush()
            out.append(blocks[int(b.group(1))])
        elif stripped.startswith("|"):
            flush()
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i])
                i += 1
            out.append(_md_table(tbl, ""))
            continue
        elif (c := re.fullmatch(r"\*\*(?:Table|Bảng)\s*\d+\s*[:.]\s*(.*?)\*\*", stripped)) and _next_is_table(lines, i):
            flush()
            i += 1
            while not lines[i].strip():
                i += 1
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i])
                i += 1
            out.append(_md_table(tbl, c.group(1)))
            continue
        elif re.match(r"^[-*]\s+", stripped) or re.match(r"^\d+[.)]\s+", stripped):
            flush()
            ordered = bool(re.match(r"^\d+[.)]\s+", stripped))
            first_number = int(re.match(r"^(\d+)", stripped).group(1)) if ordered else 1
            item_re = r"^\s*\d+[.)]\s+" if ordered else r"^\s*[-*]\s+"
            items = []
            while i < len(lines):
                if re.match(item_re, lines[i]):
                    items.append(re.sub(item_re, "", lines[i]))
                    i += 1
                elif items and lines[i].strip() and not re.match(r"^\s*(?:[-*]|\d+[.)])\s+|#|\||PAIBLOCK", lines[i].strip()) \
                        and lines[i].startswith((" ", "\t")):
                    items[-1] += " " + lines[i].strip()  # dòng tiếp nối của mục (thụt lề)
                    i += 1
                else:
                    # mục cách nhau dòng trống vẫn cùng một danh sách (không đánh số lại từ 1)
                    j = i
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j > i and j < len(lines) and re.match(item_re, lines[j]):
                        i = j
                        continue
                    break
            env = "enumerate" if ordered else "itemize"
            start = f"\\setcounter{{enumi}}{{{first_number - 1}}}\n" if ordered and first_number > 1 else ""
            out.append(f"\\begin{{{env}}}\n{start}" + "\n".join(f"\\item {inline_to_tex(t)}" for t in items) + f"\n\\end{{{env}}}")
            continue
        elif stripped.startswith("# "):
            flush()
        else:
            para.append(stripped)
        i += 1
    flush()

    kw_text = ", ".join(inline_to_tex(k) for k in keywords)
    if template == "cvpr":
        names = " \\and ".join(inline_to_tex(a) for a in authors)
        affil = "\\\\ ".join(inline_to_tex(a) for a in affs)
        front = (f"\\title{{{title}}}\n\\author{{{names}" + (f"\\\\ {affil}" if affil else "") + "}\n\\maketitle\n\n"
                 f"\\begin{{abstract}}\n{inline_to_tex(abstract)}\n\\end{{abstract}}\n")
        bib = "\\bibliographystyle{ieeenat_fullname}\n\\bibliography{references}\n"
    else:
        author_blocks = "\n\\and\n".join(
            f"\\IEEEauthorblockN{{{inline_to_tex(a)}}}" + (f"\n\\IEEEauthorblockA{{{inline_to_tex(affs[min(k, len(affs) - 1)])}}}" if affs else "")
            for k, a in enumerate(authors)
        )
        kw_block = f"\\begin{{IEEEkeywords}}\n{kw_text}\n\\end{{IEEEkeywords}}\n" if keywords else ""
        front = (f"\\title{{{title}}}\n\\author{{{author_blocks}}}\n\\maketitle\n\n"
                 f"\\begin{{abstract}}\n{inline_to_tex(abstract)}\n\\end{{abstract}}\n{kw_block}")
        bib = "\\bibliographystyle{IEEEtran}\n\\bibliography{references}\n"
    back = back_matter(body_md)
    if back:  # mục cuối bài đứng trước phụ lục (nếu có)
        out.insert(out.index("\\appendix") if "\\appendix" in out else len(out), back)
    return (
        f"{_PREAMBLES[template]}\\begin{{document}}\n{front}\n"
        + "\n\n".join(out)
        + (f"\n\n{bib}" if refs else "\n")
        + "\n\\end{document}\n"
    )


TAXONOMY_MIN_LEAVES = 6  # cây ít lá hơn vẫn vẽ bằng Mermaid được

_BACK_MATTER = (
    (r"data (?:and code )?availability|code availability",
     "Data and Code Availability",
     "No new data were collected. The analysed studies are listed in the References. The quantitative evidence ledger "
     "(each extracted value with its source paper and page) and the sources of all figures and tables were produced by "
     "the PaperAI pipeline together with this manuscript and are available on request."),
    (r"funding", "Funding", "[To be completed by the authors.]"),
    (r"conflicts? of interest|competing interests?|declaration of interest", "Conflicts of Interest", "[To be completed by the authors.]"),
    (r"author contributions?|credit authorship", "Author Contributions",
     "This manuscript was drafted by the PaperAI research assistant. [Contributions of the human authors to be completed.]"),
)


def back_matter(body_md: str) -> str:
    """Mục cuối bài mà tạp chí yêu cầu; chỉ thêm mục bài chưa có. Funding/CoI/Contributions là chỗ trống cho tác giả điền."""
    headings = " | ".join(h.lower() for h in re.findall(r"^#{2,4}\s+(.+)$", body_md, re.M))
    parts = [
        f"\\section*{{{title}}}\n{inline_to_tex(text)}"
        for pattern, title, text in _BACK_MATTER
        if not re.search(pattern, headings)
    ]
    return "\n\n".join(parts)


def _next_is_table(lines: list[str], i: int) -> bool:
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    return j < len(lines) and lines[j].strip().startswith("|")


def _write_latex_project(
    work: Path, report_md: str, chart_format: str, add_survey_table: bool, template: str, render_diagrams: bool
) -> None:
    tex = report_to_latex(report_md, work, chart_format, add_survey_table, template, render_diagrams)
    (work / "paper.tex").write_text(tex, encoding="utf-8")
    (work / "references.bib").write_text(references_to_bibtex(parse_references(report_md)), encoding="utf-8")


def export_latex_bundle(
    report_md: str, chart_format: str = "pdf", add_survey_table: bool = False, template: str = "ieee",
    render_diagrams: bool = False,
) -> bytes:
    """Zip: paper.tex, references.bib, figures/. Biên dịch: pdflatex → bibtex → pdflatex ×2 (template cvpr cần cvpr.sty của hội nghị)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        _write_latex_project(work, report_md, chart_format, add_survey_table, template, render_diagrams)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(work.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(work).as_posix())
        return buf.getvalue()


def tectonic_executable() -> str | None:
    """Tectonic: biến môi trường PAPERAI_TECTONIC, PATH, hoặc ~/.local/bin (cài tay khi chạy local)."""
    configured = os.environ.get("PAPERAI_TECTONIC")
    if configured:
        return configured if Path(configured).is_file() else shutil.which(configured)
    found = shutil.which("tectonic")
    local = Path.home() / ".local" / "bin" / "tectonic"
    return found or (str(local) if local.is_file() else None)


def _system_author() -> tuple[list[str], list[str]]:
    """Tác giả mặc định của hệ thống PaperAI (từ cấu hình) khi bài không có tác giả thật; email chỉ thêm khi được cấu hình."""
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.paper_author_name:
        return [], []
    aff = settings.paper_author_affiliation
    if settings.paper_author_email:
        aff = f"{aff}, {settings.paper_author_email}" if aff else settings.paper_author_email
    return [settings.paper_author_name], [aff] if aff else []


def compile_latex_pdf(report_md: str, template: str = "ieee", timeout: int = 600) -> bytes:
    """Biên dịch báo cáo thành PDF bằng LaTeX thật (IEEEtran qua Tectonic/XeTeX, tự chạy BibTeX).

    Hình/bảng là float LaTeX nên không còn khoảng trắng do hình nhảy trang như bản in HTML.
    Lỗi biên dịch → RuntimeError kèm vài dòng lỗi cuối để gọi phía trên chuyển sang renderer dự phòng.
    """
    import subprocess
    import tempfile

    exe = tectonic_executable()
    if not exe:
        raise RuntimeError("Chưa cài Tectonic để biên dịch LaTeX (đặt PAPERAI_TECTONIC hoặc thêm tectonic vào PATH)")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        _write_latex_project(work, report_md, "pdf", False, template, True)
        result = subprocess.run(
            [exe, "-X", "compile", "--untrusted", "paper.tex"],
            cwd=work, capture_output=True, text=True, timeout=timeout, check=False,
        )
        pdf = work / "paper.pdf"
        if result.returncode != 0 or not pdf.is_file():
            errors = [line for line in (result.stderr + result.stdout).splitlines() if "error" in line.lower()]
            raise RuntimeError("Biên dịch LaTeX thất bại: " + " | ".join(errors[-5:] or [result.stderr[-500:]]))
        return pdf.read_bytes()
