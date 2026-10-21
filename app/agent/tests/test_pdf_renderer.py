"""Content and pagination regressions for the browser-based research PDF export."""

import json
from itertools import pairwise

import pytest
from playwright.sync_api import sync_playwright

from app.pipeline.export.browser_renderer import (
    launch_browser,
    mermaid_to_svg,
    prepare_report_page,
)
from app.pipeline.export.pdf_renderer import report_to_html, report_to_pdf


@pytest.fixture
def browser():
    with sync_playwright() as p:
        browser = launch_browser(p)
        yield browser
        browser.close()


def test_json_table_preserves_groups_spans_and_math(browser):
    spec = {
        "caption": "Recall@10 comparison",
        "columns": ["Method", "Recall@10", "Formula"],
        "header_groups": [{"label": "Models", "span": 1}, {"label": "Metrics", "span": 2}],
        "rows": [["Group A", 0.8, r"$\frac{x_i}{n}$"], ["", 0.9, "**Best**"]],
        "bold_rows": [1],
    }
    page = browser.new_page()
    try:
        warnings = prepare_report_page(page, report_to_html("```table\n" + json.dumps(spec) + "\n```"))
        assert not warnings
        assert page.locator('th[colspan="2"]').inner_text() == "Metrics"
        assert page.locator('td[rowspan="2"]').inner_text() == "Group A"
        assert page.locator("td .katex").count() == 1
        assert "Recall@10 comparison" in page.locator(".caption").inner_text()
    finally:
        page.close()


@pytest.mark.parametrize("kind", ["table", "chart"])
def test_invalid_spec_remains_visible(kind):
    document = report_to_html(f"```{kind}\nINVALID-SPEC-CONTENT\n```")
    assert "INVALID-SPEC-CONTENT" in document
    assert 'class="render-warning"' in document


def test_code_is_not_converted_to_math():
    document = report_to_html('```python\nformula = "$$x$$"\n```')
    assert 'class="language-python"' in document
    assert "$$x$$" in document
    assert '<div class="math">' not in document


@pytest.mark.parametrize("columns", [1, 2])
def test_layout_preserves_front_matter_and_spans_wide_tables(browser, columns):
    spec = {
        "columns": ["Method", "Supervision", *[f"Metric {i}" for i in range(10)]],
        "rows": [["Method A", "Zero-Shot", *range(10)], ["Method B", "Supervised", *range(10)]],
        "caption": "Wide benchmark",
    }
    report = "# Two column paper\n\n## Abstract\nFull width abstract.\n\n## 1. Introduction\n"
    report += "Research paragraph with evidence. " * 80
    report += "\n\n```table\n" + json.dumps(spec) + "\n```"
    page = browser.new_page()
    try:
        assert not prepare_report_page(page, report_to_html(report, columns=columns))
        assert page.locator(".paper-body .abstract, .paper-body .title").count() == 0
        body = page.locator(".paper-body")
        assert body.evaluate("el => getComputedStyle(el).columnCount") == ("2" if columns == 2 else "auto")
        table = page.locator("table")
        assert table.bounding_box()["width"] >= body.bounding_box()["width"] * 0.98
        cells = table.locator("tbody tr").first.locator("td").all()
        for left, right in pairwise(cells):
            a, b = left.bounding_box(), right.bounding_box()
            assert a["x"] + a["width"] <= b["x"] + 1
        assert page.locator(".tbl.keep-together").count() == 1
    finally:
        page.close()


def test_two_column_pdf_has_text_in_both_columns():
    import pymupdf

    paragraphs = "\n\n".join(f"Paragraph{i:03d}: " + "Research evidence supports this method. " * 12 for i in range(20))
    pdf = report_to_pdf("# Layout regression\n\n## 1. Introduction\n\n" + paragraphs)
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        first = document[0]
        words = [word for word in first.get_text("words") if word[4].startswith("Paragraph")]
        assert any(word[0] < first.rect.width / 2 for word in words)
        assert any(word[0] > first.rect.width / 2 for word in words)
        text = "\n".join(page.get_text() for page in document)
        assert "Paragraph000" in text and "Paragraph019" in text


def test_original_mermaid_graph_is_preserved():
    import xml.etree.ElementTree as ET

    code = 'graph TD\nA["Source"] --> B["Branch one"]\nA --> C["Branch two"]\nB --> D["Merge"]\nC --> D'
    svg = mermaid_to_svg(code)
    labels = ["".join(node.itertext()) for node in ET.fromstring(svg).iter() if node.tag.endswith("text")]
    assert all(label in labels for label in ("Source", "Branch one", "Branch two", "Merge"))
    assert "foreignObject" not in svg
    assert svg.count('class="edge-thickness-normal') == 4


@pytest.mark.parametrize("fraction", [r"\frac{x_{i}}{\sqrt{n}}", r"\frac(x_(i))(\sqrt(n))"])
def test_mermaid_labels_render_math_instead_of_tex(browser, fraction):
    diagram = 'graph TD\n' + r'A["Visual $f_v$"] -->|"$\phi(i)$"| ' + f'B["Score ${fraction}$"]'
    page = browser.new_page()
    try:
        assert not prepare_report_page(page, report_to_html("```mermaid\n" + diagram + "\n```"))
        graph = page.locator(".mermaid-rendered")
        assert graph.locator("math").count() == 3
        assert graph.locator("mfrac").count() == 1
        assert graph.locator("msqrt").count() == 1
        text = " ".join(graph.locator(".nodeLabel, .edgeLabel").all_text_contents())
        assert "$" not in text and r"\frac" not in text and r"\phi" not in text
        assert any(symbol in text for symbol in ("\u03c6", "\u03d5"))
        normalized = page.evaluate("""async code => {
            const {normalizeMermaidMath} = await import('https://paperai-assets.invalid/mermaid-math.js');
            const once = normalizeMermaidMath(code);
            return {once, twice: normalizeMermaidMath(once)};
        }""", diagram)
        assert normalized["once"] == normalized["twice"]
        assert r"\frac{x_{i}}{\sqrt{n}}" in normalized["once"]
    finally:
        page.close()


def test_typst_mermaid_math_is_not_lost_in_svg(tmp_path):
    from app.pipeline.export.typst_renderer import render_report_to_pdf

    diagram = 'graph TD\n' + r'A["Visual $f_v$"] --> B["Score $\frac(1)(\sqrt(n))$"]'
    svg = mermaid_to_svg(diagram)
    assert "<foreignObject" not in svg
    assert 'href="data:image/png;base64,' in svg
    pdf = render_report_to_pdf("# Math diagram\n\n## 1. Method\n\n```mermaid\n" + diagram + "\n```")
    assert pdf.startswith(b"%PDF-")


def test_invalid_mermaid_keeps_original_source(browser):
    page = browser.new_page()
    try:
        warnings = prepare_report_page(page, report_to_html("```mermaid\nNOT-A-VALID-DIAGRAM\n```"))
        assert warnings
        assert "NOT-A-VALID-DIAGRAM" in page.locator("pre.render-error").inner_text()
        assert page.locator(".render-warning").count() == 1
    finally:
        page.close()


def test_large_diagram_and_long_table_fit_pdf(tmp_path):
    import pymupdf

    graph = "graph TD\n" + "\n".join(f'N{i}["Stage {i:02d}"] --> N{i+1}["Stage {i+1:02d}"]' for i in range(25))
    table = "| Method | Recall@10 |\n|---|---|\n" + "\n".join(f"| Row{i:03d} | {i} |" for i in range(100))
    chart = {"type": "stacked_barh", "labels": ["A", "B"], "series": [
        {"name": "Wins", "values": ["60%", None]}, {"name": "Losses", "values": [40, 100]},
    ]}
    report = "# Export regression\n\n## 1. Results\n\n```mermaid\n" + graph + "\n```\n\n" + table
    report += "\n\n```chart\n" + json.dumps(chart) + "\n```\n\n$$\n\\frac{x_i}{\\sqrt{n}}\n$$"
    with sync_playwright() as p:
        browser = launch_browser(p)
        try:
            page = browser.new_page()
            assert not prepare_report_page(page, report_to_html(report))
            assert page.locator(".katex-error, .render-error").count() == 0
            bounds = page.locator(".mermaid-rendered svg").bounding_box()
            assert bounds["height"] <= 220 * 96 / 25.4 + 1
            assert bounds["width"] <= 658
        finally:
            browser.close()
    pdf = report_to_pdf(report)
    (tmp_path / "regression.pdf").write_bytes(pdf)
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        assert len(document) > 2
        text = "\n".join(page.get_text() for page in document)
        assert "Stage 00" in text and "Stage 25" in text
        assert "Row000" in text and "Row099" in text
        assert text.count("Recall@10") > 1  # Table headings repeat across page breaks.
