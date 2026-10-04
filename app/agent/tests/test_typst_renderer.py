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
