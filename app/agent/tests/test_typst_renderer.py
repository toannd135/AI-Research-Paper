"""Unit tests for Typst Academic Engine Renderer."""

import tempfile
from pathlib import Path
import pytest
from app.pipeline.export.typst_renderer import (
    latex_to_typst_math,
    parse_markdown_table_to_typst,
    render_chart_spec_to_svg,
    markdown_to_typst,
    render_report_to_pdf,
)


def test_latex_to_typst_math_basics():
    # Fractions
    assert latex_to_typst_math(r"\frac{a}{b}") == "(a) / (b)"
    assert latex_to_typst_math(r"\frac{1}{N}") == "(1) / (N)"

    # Blackboard bold & calligraphy
    assert "RR" in latex_to_typst_math(r"\mathbb{R}^{d \times d}")
    assert "cal(D)" in latex_to_typst_math(r"\mathcal{D}")

    # Greek letters
    assert "Delta" in latex_to_typst_math(r"\Delta W")
    assert "alpha" in latex_to_typst_math(r"\alpha")
    assert "lambda" in latex_to_typst_math(r"\lambda")

    # Sum and subscripts
    res = latex_to_typst_math(r"\sum_{i=1}^N x_i")
    assert "sum_(i=1)^N" in res

    # Comparison and operations
    assert "<=" in latex_to_typst_math(r"a \le b")
    assert ">=" in latex_to_typst_math(r"a \ge b")
    assert "dot" in latex_to_typst_math(r"a \cdot b")
    assert "times" in latex_to_typst_math(r"d \times d")

    # Square root and accents
    assert "sqrt(r)" in latex_to_typst_math(r"\sqrt{r}")
    assert "macron(r)" in latex_to_typst_math(r"\bar{r}")


def test_latex_to_typst_math_complex_equation():
    raw = r"P(\{r_l\}) = \sum_{l=1}^L 2 \cdot (d \cdot r_l + r_l \cdot d) = 4d \sum_{l=1}^L r_l."
    typ = latex_to_typst_math(raw)
    assert "sum_(l=1)^L" in typ
    assert "dot" in typ


@pytest.mark.parametrize("formula", [
    r"\frac{x_{i}}{\sqrt{n}}",
    r"\frac{\frac{a}{b}}{\frac{c}{d}}",
    r"\frac{1}{N_{total}} + \frac{x^{2}}{y_{i}}",
    r"\frac {x_{i}} {n}",
    r"\dfrac{x_{i}}{n}",
    r"\tfrac{x_{i}}{n}",
    r"\frac{\{x\}}{n}",
])
def test_nested_fraction_pdf_compilation(formula):
    converted = latex_to_typst_math(formula)
    assert not any(macro in converted for macro in (r"\frac", r"\dfrac", r"\tfrac"))
    report = "# Fraction regression\n\n## 1. Method\n\n$$\n" + formula + "\n$$"
    assert render_report_to_pdf(report).startswith(b"%PDF-")


def test_nested_fraction_in_abstract_inline_and_table():
    report = r"""# Fraction contexts

## Abstract
The estimate is $\frac{x_{i}}{\sqrt{n}}$.

## 1. Method
Inline estimate: $\frac{x_{i}}{\sqrt{n}}$.

| Estimate | Value |
|---|---|
| $\frac{x_{i}}{\sqrt{n}}$ | 1 |
"""
    assert render_report_to_pdf(report).startswith(b"%PDF-")


@pytest.mark.parametrize("content", [
    "Recall@10 and NDCG@10; contact researcher@example.org. See [10].",
    r"Already escaped: Recall\@10.",
    "## Recall@10\nThe ranking result.",
    "| Metric | Value |\n|---|---|\n| Recall@10 | 0.8 |",
    "**Table 1: Recall@10**\n\n| Metric | Value |\n|---|---|\n| NDCG@10 | 0.8 |",
    "```python\nmetric = 'Recall@10'\n```",
])
def test_literal_at_sign_pdf_compilation(content):
    report = "# Ranking\n\n## Abstract\nRecall@10 evaluation.\n\n## 1. Results\n\n" + content
    source = markdown_to_typst(report)
    assert r"Recall\@10 evaluation." in source
    assert render_report_to_pdf(report).startswith(b"%PDF-")


def test_literal_at_sign_in_chart_caption():
    report = '''# Ranking

## 1. Results

```chart
{"labels": ["Baseline"], "series": [{"values": [0.8]}], "caption": "Recall@10 results"}
```
'''
    assert render_report_to_pdf(report).startswith(b"%PDF-")


def test_parse_markdown_table_to_typst():
    table_md = """
| Method ($M_{total}$) | Params ($K_{ret}$) | Accuracy (%) |
| :--- | :---: | :---: |
| Baseline | 144.0 | 88.5 |
| Ours | 0.74 | **91.2** |
"""
    typ_table = parse_markdown_table_to_typst(table_md, caption="Memory comparison with $M_{total}$")
    assert "#figure(" in typ_table
    assert "table(" in typ_table
    assert "table.hline(stroke: 1.2pt)" in typ_table
    assert "table.hline(stroke: 0.6pt)" in typ_table
    assert 'caption: [Memory comparison with $M_("total")$]' in typ_table
    assert '[*Method ($M_("total")$)*]' in typ_table
    assert '[*Params ($K_("ret")$)*]' in typ_table
    assert "[*91.2*]" in typ_table


def test_typst_renders_json_table_as_table():
    import json

    spec = {
        "columns": ["Method", "R@10", "R@50"],
        "header_groups": [{"label": "Method", "span": 1}, {"label": "Recall", "span": 2}],
        "rows": [["Baseline", 10, 20], ["", 12, 23]],
        "caption": "Recall@10 results",
        "bold_rows": [1],
    }
    report = "# Tables\n\n## 1. Results\n\n```table\n" + json.dumps(spec) + "\n```"
    source = markdown_to_typst(report)
    assert "```table" not in source
    assert "table.cell(colspan: 2)" in source
    assert "table.cell(rowspan: 2)" in source
    assert render_report_to_pdf(report).startswith(b"%PDF-")


def test_render_chart_spec_to_svg():
    with tempfile.TemporaryDirectory() as td:
        out_svg = Path(td) / "test_chart.svg"
        spec = {
            "type": "line",
            "title": "Ablation on Rank",
            "labels": ["2", "4", "8", "16"],
            "series": [{"name": "Method A", "values": [85.0, 88.2, 90.1, 90.4]}],
            "x_label": "Rank",
            "y_label": "Accuracy (%)"
        }
        res = render_chart_spec_to_svg(spec, out_svg)
        assert res.exists()
        content = res.read_text(encoding="utf-8")
        assert "<svg" in content


def test_markdown_to_typst_structure():
    sample_md = """# Novel Attention Mechanism for PEFT

**Authors:** Alice Researcher, Bob Scientist | **Affiliations:** AI Lab, Tech University

## Abstract
This paper introduces an innovative approach to parameter-efficient fine-tuning.

**Keywords:** PEFT, Transformer, LoRA

## 1. Introduction
Parameter efficiency is critical in modern deep learning.

$$
L_{reg} = \\frac{1}{2} ||W||_F^2
$$

- Contribution 1: New architecture
- Contribution 2: Extensive ablations

## 2. Methodology
Consider a matrix $W \\in \\mathbb{R}^{d \\times d}$.

| Model | Acc |
|---|---|
| A | 90 |
| B | 92 |
"""
    typ_doc = markdown_to_typst(sample_md)
    assert "Novel Attention Mechanism for PEFT" in typ_doc
    assert "Alice Researcher" in typ_doc
    assert "AI Lab" in typ_doc
    assert "This paper introduces" in typ_doc
    assert "= 1. Introduction" in typ_doc
    assert "= 2. Methodology" in typ_doc
    assert "table(" in typ_doc
    assert "- Contribution 1" in typ_doc


def test_render_report_to_pdf_compilation():
    sample_md = """# Adaptive Rank Optimization

**Authors:** Research Team | **Affiliations:** AI Institute

## Abstract
We present an adaptive framework for low-rank fine-tuning of neural networks.

**Keywords:** Neural Networks, Optimization, PEFT

## 1. Introduction
Fine-tuning large language models requires substantial computational resources.

$$
f(x) = W x + b
$$

As shown in the formulation, rank allocation is vital.

## 2. Experiments
Experimental validation demonstrates superior convergence.

| Baseline | Accuracy |
| :--- | :---: |
| Fixed | 88.2% |
| Ours | 91.5% |

## 3. Conclusion
The proposed method consistently outperforms static baselines.
"""
    with tempfile.TemporaryDirectory() as td:
        pdf_out = Path(td) / "test_output.pdf"
        pdf_bytes = render_report_to_pdf(sample_md, output_pdf_path=pdf_out)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b"%PDF-")
        assert pdf_out.exists()


def test_llm_latex_leftovers_compile_in_typst():
    report = (
        "# LaTeX leftovers\n\n## 1. Method\n\n"
        r"Density (cells/mm$^2$) with $MSI \to TME$, $\hat{\rho}_{CD45RO}$, $g \leftrightarrow h$, $a \ll b$."
        "\n\n"
        r"$$ \pi^* = \arg\min_{\pi} \langle \pi, M \rangle, \quad s = \Big[ \tanh(x) \Big]^\top $$"
        "\n"
    )
    assert render_report_to_pdf(report).startswith(b"%PDF-")


def test_wide_tables_span_both_columns_and_narrow_ones_do_not():
    wide = "| A | B | C | D |\n|---|---|---|---|\n| 1 | 2 | 3 | 4 |"
    narrow = "| A | B |\n|---|---|\n| 1 | 2 |"
    assert 'scope: "parent"' in parse_markdown_table_to_typst(wide, "Wide")
    assert 'scope: "parent"' not in parse_markdown_table_to_typst(narrow, "Narrow")
    report = "# Wide table\n\n## 1. Results\n\n" + wide + "\n"
    assert render_report_to_pdf(report).startswith(b"%PDF-")


def test_long_display_equation_is_broken_and_compiles():
    from app.pipeline.export.typst_renderer import _break_long_equation

    items = ", ".join(rf"\text{{Mean}}(x_{i})" for i in range(12))
    broken = _break_long_equation(f"s = [{items}]")
    assert "\\\n" in broken
    short = "a = b + c"
    assert _break_long_equation(short) == short
    report = "# Long equation\n\n## 1. Method\n\n$$ s = [" + items + "] $$\n"
    assert render_report_to_pdf(report).startswith(b"%PDF-")
