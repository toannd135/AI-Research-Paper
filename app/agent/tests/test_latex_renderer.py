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
