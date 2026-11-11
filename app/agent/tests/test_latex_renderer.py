"""Xuất gói LaTeX IEEEtran + BibTeX + bảng khảo sát."""

import io
import json
import zipfile

from app.pipeline.export.bibliography import parse_references, references_to_bibtex, survey_table_block
from app.pipeline.export.latex_renderer import export_latex_bundle, inline_to_tex

REPORT = """# Edge **AI** Survey

**Authors:** An B, Cy D | **Affiliations:** Lab X

## Abstract

We study $x_i$ at 95% accuracy [1].

**Keywords:** edge, ai

## 1. Introduction

Prior work [1, 2] and [1]-[2] reached R&D_ready results.

- item one
- item **two**

**Table 1: Results**

| Method | F1 |
|---|---|
| A | 0.9 |

```chart
{"type": "bar", "caption": "F1 by method [1]", "labels": ["A", "B"], "series": [{"name": "F1", "values": [1, 2], "errors": [0.1, 0.2]}]}
```

$$
y = x^2
$$

## References

[1] Smith et al., "Deep Nets," *arXiv preprint*, 2023, DOI: 10.1/x.
[2] A B and C D, "Foo," *IEEE TPAMI*, 2021.
"""


def test_inline_escapes_and_cites():
    out = inline_to_tex("R&D_x 5% **b** *i* [1, 3] [1]-[2] $a_b$ ≥")
    assert r"R\&D\_x 5\%" in out and r"\textbf{b}" in out and r"\emph{i}" in out
    assert r"\cite{ref1,ref3}" in out and "$a_b$" in out and r"$\geq$" in out


def test_bibtex_keys_match_cites():
    bib = references_to_bibtex(parse_references(REPORT))
    assert "@misc{ref1," in bib and "@article{ref2," in bib and "author = {Smith and others}" in bib


def test_bundle_contents():
    z = zipfile.ZipFile(io.BytesIO(export_latex_bundle(REPORT, add_survey_table=True)))
    names = set(z.namelist())
    assert {"paper.tex", "references.bib", "figures/chart_1.pdf"} <= names
    assert z.read("figures/chart_1.pdf").startswith(b"%PDF")
    tex = z.read("paper.tex").decode()
    assert r"\documentclass[conference]{IEEEtran}" in tex and r"\bibliography{references}" in tex
    assert r"\section{Introduction}" in tex and r"\begin{equation}" in tex and r"\begin{itemize}" in tex
    assert r"\caption{Results}" in tex and r"\toprule" in tex and "Summary of the surveyed literature" in tex
    assert "## References" not in tex


def test_eps_chart_format():
    z = zipfile.ZipFile(io.BytesIO(export_latex_bundle(REPORT, chart_format="eps")))
    assert z.read("figures/chart_1.eps").startswith(b"%!PS")


def test_survey_block_is_valid_table_json():
    block = survey_table_block(parse_references(REPORT))
    spec = json.loads(block.split("\n", 1)[1].rsplit("\n```", 1)[0])
    assert spec["columns"][0] == "Ref." and spec["rows"][0][2] == "2021"


APPENDIX_REPORT = REPORT.replace("## References", "## Appendix A. Implementation Details\n\n**Datasets.** Used [1].\n\n## References")


def test_appendix_and_cvpr_template():
    z = zipfile.ZipFile(io.BytesIO(export_latex_bundle(APPENDIX_REPORT, template="cvpr")))
    tex = z.read("paper.tex").decode()
    assert r"\usepackage[review]{cvpr}" in tex and r"\bibliographystyle{ieeenat_fullname}" in tex
    assert r"\appendix" in tex and r"\section{Implementation Details}" in tex
    assert tex.index(r"\appendix") < tex.index(r"\section{Implementation Details}")
    assert r"\author{An B \and Cy D" in tex


def test_unknown_template_rejected():
    import pytest

    with pytest.raises(ValueError):
        export_latex_bundle(REPORT, template="acm")


LONG_TABLE = {
    "caption": "Many methods",
    "columns": ["Method [Ref]", "Setting", "Metric", "Value", "Δ vs best"],
    "rows": [[f"Method {i} with a fairly long descriptive name [{i}]", "FeTA 2021 (testing)", "Dice AVG", "0.86", "-0.01"]
             for i in range(120)],
}


def test_tables_wrap_text_and_split_across_pages():
    tex = zipfile.ZipFile(io.BytesIO(export_latex_bundle(
        "# T\n\n## 1. Intro\n\nText.\n\n```table\n" + json.dumps(LONG_TABLE) + "\n```\n"))).read("paper.tex").decode()
    assert r"\begin{tabularx}{\textwidth}" in tex and r"\raggedright\arraybackslash}X" in tex
    assert tex.count(r"\begin{table*}") >= 2 and "(continued)" in tex
    assert r"\addtocounter{table}{-1}" in tex


def test_numbered_list_with_blank_lines_keeps_numbering():
    md = "# T\n\n## 1. Intro\n\n1. **First** item.\n\n2. Second item.\n\n3. Third item.\n\nAfter list.\n"
    tex = zipfile.ZipFile(io.BytesIO(export_latex_bundle(md))).read("paper.tex").decode()
    assert tex.count(r"\begin{enumerate}") == 1 and tex.count(r"\item") == 3


def test_mermaid_caption_with_trailing_text_and_escaped_placeholder():
    md = ("# T\n\n## 1. Intro\n\n**Figure 1: Flow.** Counts come from this run.\n\n"
          "```mermaid\nflowchart TD\n  A[\"x_1\"] --> B\n```\n")
    tex = zipfile.ZipFile(io.BytesIO(export_latex_bundle(md))).read("paper.tex").decode()
    assert r"\caption{Flow. Counts come from this run.}" in tex
    assert r"flow\_1.mmd" in tex  # dấu _ đã escape, không làm hỏng biên dịch


def test_compile_latex_pdf_produces_pdf():
    import pytest

    from app.pipeline.export.latex_renderer import compile_latex_pdf, tectonic_executable

    if not tectonic_executable():
        pytest.skip("Tectonic chưa được cài")
    pdf = compile_latex_pdf(REPORT + "\n```table\n" + json.dumps(LONG_TABLE) + "\n```\n")
    assert pdf.startswith(b"%PDF")


def test_missing_authors_filled_with_paperai_system_author(monkeypatch):
    from app.core.config import get_settings

    def _tex(md: str) -> str:
        return zipfile.ZipFile(io.BytesIO(export_latex_bundle(md))).read("paper.tex").decode()

    assert r"\IEEEauthorblockN{PaperAI}" in _tex("# T\n\n## 1. Intro\n\nText.\n")
    assert r"\IEEEauthorblockA{PaperAI Automated Research Assistant}" in _tex("# T\n\n## 1. Intro\n\nText.\n")
    # tên giữ chỗ cũ của pipeline cũng được thay bằng tác giả hệ thống
    placeholder = "# T\n\n**Authors:** PaperAI Automated Research Protocol | **Affiliations:** Open-Source Automated Science Initiative\n\n## 1. Intro\n\nText.\n"
    assert r"\IEEEauthorblockN{PaperAI}" in _tex(placeholder)
    monkeypatch.setattr(get_settings(), "paper_author_email", "bot@example.org")
    assert "PaperAI Automated Research Assistant, bot@example.org" in _tex("# T\n\n## 1. Intro\n\nText.\n")
    assert r"\IEEEauthorblockN{An B}" in _tex(REPORT)  # tác giả thật giữ nguyên


def _paper_tex(md: str) -> str:
    return zipfile.ZipFile(io.BytesIO(export_latex_bundle(md))).read("paper.tex").decode()


TAXONOMY_MD = (
    "# T\n\n## 1. Intro\n\n**Figure 1: Six-axis taxonomy [3], [4], [5], [6], [7].**\n\n```mermaid\ngraph LR\n"
    '  R["Methods"]\n  A["A. Fusion"]\n  A1["Early<br/>[2, 37]"]\n  A2["Late<br/>[5]"]\n  A3["Hybrid [1]"]\n'
    '  B["B. Backbone"]\n  B1["3D CNN"]\n  B2["Transformer"]\n  B3["Mamba"]\n'
    "  R --> A\n  R --> B\n  A --> A1\n  A --> A2\n  A --> A3\n  B --> B1\n  B --> B2\n  B --> B3\n```\n\nText.\n"
)


def test_taxonomy_tree_becomes_native_figure_without_leaf_cites():
    tex = _paper_tex(TAXONOMY_MD)
    assert r"\fbox{\textbf{Methods}}" in tex and r"\textbf{A. Fusion} & \textbf{B. Backbone}" in tex
    assert "Early & 3D CNN" in tex and r"\cite{ref37}" not in tex  # bỏ trích dẫn ở nhãn lá
    assert r"\caption{Six-axis taxonomy.}" in tex  # caption bỏ cụm 5 trích dẫn


def test_caption_keeps_short_cite_lists():
    from app.pipeline.export.latex_renderer import _trim_caption_cites

    assert _trim_caption_cites("Values from [3] and [4, Table 1].") == "Values from [3] and [4, Table 1]."
    assert _trim_caption_cites("Tree [32], [28], [30], [12].") == "Tree."
    assert _trim_caption_cites("Early [2, 37, 42, 5] methods") == "Early methods"


def test_ieee_table_refs_roman_but_captions_and_source_tables_kept():
    from app.pipeline.export.latex_renderer import roman_table_refs

    out = roman_table_refs("**Table 3: Taxonomy**\n\nSee **Table 3**, Tables 2 and 4, Table 2 of [5] and [52, Table 1].")
    assert out.startswith("**Table 3: Taxonomy**")
    assert "**Table III**" in out and "Tables II and IV" in out and "Table 2 of [5]" in out and "[52, Table 1]" in out
    md = "# T\n\n## 1. Intro\n\nAs Table 1 shows.\n\n**Table 1: Results**\n\n| A | B |\n|---|---|\n| x | 1 |\n"
    tex = _paper_tex(md)
    assert "As Table I shows." in tex and r"\caption{Results}" in tex


def test_back_matter_added_only_when_missing():
    tex = _paper_tex("# T\n\n## 1. Intro\n\nText.\n\n## 7. Funding\n\nGrant X.\n")
    assert r"\section*{Data and Code Availability}" in tex and r"\section*{Conflicts of Interest}" in tex
    assert r"\section*{Author Contributions}" in tex and r"\section*{Funding}" not in tex
    appendix = _paper_tex("# T\n\n## 1. Intro\n\nText.\n\n## Appendix A. Extra\n\nMore.\n")
    assert appendix.index(r"\section*{Data and Code Availability}") < appendix.index(r"\appendix")


def test_times_math_font_and_tex_quotes():
    tex = _paper_tex('# T\n\n## 1. Intro\n\nIt "fails" on $x$.\n')
    assert r"\usepackage{newtxmath}" in tex and "amssymb" not in tex
    assert tex.index(r"\usepackage{newtxmath}") < tex.index(r"\usepackage[no-math]{fontspec}")
    assert "It ``fails'' on $x$." in tex


def test_grouped_table_rules_between_groups():
    spec = {"caption": "G", "columns": ["Axis", "Cat"], "rows": [["A", "x"], ["", "y"], ["B", "z"]]}
    tex = _paper_tex("# T\n\n## 1. Intro\n\n```table\n" + json.dumps(spec) + "\n```\n")
    assert tex.count(r"\midrule[0.3pt]") == 1
