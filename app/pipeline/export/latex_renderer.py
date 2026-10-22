"""Report Markdown → gói LaTeX IEEEtran (paper.tex + references.bib + figures/*.pdf).

- Trích dẫn [n] → \\cite{refn}; mục '## References' thay bằng \\bibliography{references}.
- Khối ```chart → figures/chart_k.pdf (vector, font nhúng) hoặc .eps; khối ```image → PNG gốc.
- Khối ```table / bảng Markdown → booktabs (table* khi từ 4 cột).
- Sơ đồ ```mermaid không có bộ chuyển PDF thuần Python: lưu mã nguồn .mmd và chèn khung chỗ trống để xuất tay.
"""

import io
import json
import logging
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
_COMMON_PACKAGES = r"""\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,graphicx,booktabs,multirow,textcomp,xcolor}
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


def _clean_caption(raw: str) -> str:
    return inline_to_tex(_CAPTION_PREFIX_RE.sub("", raw.strip()))


def _tabular(columns: list[str], rows: list[list], groups=None, bold_rows=()) -> tuple[str, int]:
    """Bảng booktabs; ô cột đầu rỗng = gộp dọc (multirow); header_groups = multicolumn."""
    n = len(columns)
    size = r"\scriptsize" if n >= 7 else r"\footnotesize" if n >= 4 else r"\small"
    lines = [size, r"\begin{tabular}{l" + "c" * (n - 1) + "}", r"\toprule"]
    if groups and sum(int(g["span"]) for g in groups) == n:
        cells = [r"\multicolumn{%d}{c}{%s}" % (int(g["span"]), inline_to_tex(str(g.get("label", "")))) for g in groups]
        lines.append(" & ".join(cells) + r" \\")
    lines.append(" & ".join(r"\textbf{%s}" % inline_to_tex(c) for c in columns) + r" \\")
    lines.append(r"\midrule")
    for i, row in enumerate(rows):
        cells = []
        for j, v in enumerate(row):
            text = "" if v is None else str(v)
            if j == 0 and not text.strip() and i > 0:
                cells.append("")
                continue
            body = inline_to_tex(text)
            if i in bold_rows:
                body = r"\textbf{%s}" % body
            if j == 0 and text.strip():
                span = 1
                while i + span < len(rows) and not str(rows[i + span][0] or "").strip():
                    span += 1
                if span > 1:
                    body = r"\multirow{%d}{*}{%s}" % (span, body)
            cells.append(body)
        lines.append(" & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines), n


def _table_env(columns, rows, caption: str, groups=None, bold_rows=()) -> str:
    tab, n = _tabular(columns, rows, groups, bold_rows)
    env = "table*" if n >= 4 else "table"
    return f"\\begin{{{env}}}[t]\n\\centering\n\\caption{{{_clean_caption(caption)}}}\n{tab}\n\\end{{{env}}}"


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


def report_to_latex(
    report_md: str, work_dir: Path, chart_format: str = "pdf", add_survey_table: bool = False, template: str = "ieee"
) -> str:
    """Trả về nội dung paper.tex (template: ieee | cvpr); ghi figures/ vào work_dir."""
    if template not in _PREAMBLES:
        raise ValueError(f"Template LaTeX không hỗ trợ: {template}")
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

    def figure(file: str, caption: str, width: str = r"\columnwidth") -> str:
        return (f"\\begin{{figure}}[t]\n\\centering\n\\includegraphics[width={width}]{{{file}}}\n"
                f"\\caption{{{_clean_caption(caption)}}}\n\\end{{figure}}")

    def repl_chart(m):
        counter[0] += 1
        spec = json.loads(m.group(1))
        name = f"chart_{counter[0]}"
        data = _render_chart_svg(spec, chart_format)
        (fig_dir / f"{name}.{chart_format}").write_bytes(data)
        return keep(figure(f"figures/{name}", str(spec.get("caption") or spec.get("title") or "Evaluation results")))

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
        return keep(figure(f"figures/{name}", str(spec.get("caption", "")), r"0.9\columnwidth"))

    def repl_mermaid(m):
        counter[0] += 1
        name = f"flow_{counter[0]}"
        (fig_dir / f"{name}.mmd").write_text(m.group(2).strip() + "\n", encoding="utf-8")
        cap = _clean_caption(m.group(1) or "System diagram")
        return keep("\\begin{figure}[t]\n\\centering\n"
                    f"\\fbox{{\\parbox{{0.9\\columnwidth}}{{\\centering Diagram: export figures/{name}.mmd to PDF "
                    f"and replace this box with \\texttt{{\\textbackslash includegraphics}}}}}}\n\\caption{{{cap}}}\n\\end{{figure}}")

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
    body = re.sub(r"(?:^[ \t]*\*\*(?:Figure|Fig\.|Hình)\s*\d+\s*[:.]\s*([^\n]*?)\*\*[ \t]*\n+)?```mermaid[ \t]*\n(.*?)```",
                  repl_mermaid, body, flags=re.DOTALL | re.MULTILINE)
    body = re.sub(r"```table[ \t]*\n(.*?)```", repl_json_table, body, flags=re.DOTALL)
    body = re.sub(r"```([a-zA-Z0-9_-]*)[ \t]*\n(.*?)```", repl_code, body, flags=re.DOTALL)
    body = re.sub(r"\$\$(.+?)\$\$", lambda m: keep("\\begin{equation}\n" + m.group(1).strip() + "\n\\end{equation}"), body, flags=re.DOTALL)

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
            items = []
            while i < len(lines) and re.match(r"^\s*(?:[-*]|\d+[.)])\s+", lines[i]):
                items.append(re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", lines[i]))
                i += 1
            env = "enumerate" if ordered else "itemize"
            out.append(f"\\begin{{{env}}}\n" + "\n".join(f"\\item {inline_to_tex(t)}" for t in items) + f"\n\\end{{{env}}}")
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
    return (
        f"{_PREAMBLES[template]}\\begin{{document}}\n{front}\n"
        + "\n\n".join(out)
        + (f"\n\n{bib}" if refs else "\n")
        + "\n\\end{document}\n"
    )


def _next_is_table(lines: list[str], i: int) -> bool:
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    return j < len(lines) and lines[j].strip().startswith("|")


def export_latex_bundle(report_md: str, chart_format: str = "pdf", add_survey_table: bool = False, template: str = "ieee") -> bytes:
    """Zip: paper.tex, references.bib, figures/. Biên dịch: pdflatex → bibtex → pdflatex ×2 (template cvpr cần cvpr.sty của hội nghị)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        tex = report_to_latex(report_md, work, chart_format, add_survey_table, template)
        (work / "paper.tex").write_text(tex, encoding="utf-8")
        (work / "references.bib").write_text(references_to_bibtex(parse_references(report_md)), encoding="utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(work.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(work).as_posix())
        return buf.getvalue()
