from app.agent.evidence.report_structure import (
    check_cross_references,
    finalize_structure,
    finalize_structure_report,
    renumber_captions,
    renumber_captions_report,
    renumber_sections,
    source_diversity_warning,
    strip_dangling_citations,
)


def test_renumber_sections_fixes_misplaced_subsection():
    text = "## 1. Intro\n### 1.1 A\n## 2. Tax\n### 2.1 B\n### 1.4 Paper Organization\n## 3. M\n### 3.1 C"
    out = renumber_sections(text)
    assert "### 2.2 Paper Organization" in out
    assert "## 3. M" in out and "### 3.1 C" in out


def test_renumber_sections_skips_code_fences_and_unnumbered():
    text = "## Abstract\n## 1. Intro\n```mermaid\n## 9. not heading\n```\n## References"
    assert renumber_sections(text) == text


def test_renumber_captions_dedupes_and_remaps_unique_refs():
    text = "**Table 1: A**\n\n**Table 2: B**\n\nSee Table 2.\n\n**Figure 1: X**\n\n**Figure 1: Y**\n\nSee Figure 1."
    out = renumber_captions(text)
    assert "**Figure 2: Y**" in out
    assert "See Figure 2." in out  # mơ hồ → gán theo caption gần nhất (không còn giữ số cũ)
    assert "See Table 2." in out


def test_renumber_captions_updates_reference_after_shift():
    text = "**Table 1: A**\n\n**Table 1: B**\n\n**Table 3: C**\n\nSee Table 3."
    out = renumber_captions(text)
    assert "**Table 3: C**" in out
    text2 = "**Table 2: A**\n\nSee Table 2."
    assert renumber_captions(text2) == "**Table 1: A**\n\nSee Table 1."


def test_strip_dangling_citations():
    out, removed = strip_dangling_citations("Claim [1] and more [4], done [2].", 2)
    assert out == "Claim [1] and more, done [2]."
    assert removed == [4]
    out, removed = strip_dangling_citations("A [1].", 0)
    assert out == "A." and removed == [1]


def test_source_diversity_warning():
    assert source_diversity_warning("x [1]", 0)
    assert source_diversity_warning(" ".join(["a [1]"] * 12), 1)
    assert source_diversity_warning(" ".join(f"a [{i % 4 + 1}]" for i in range(12)), 4) is None


def test_finalize_structure_runs_both():
    out = finalize_structure("## 1. A\n### 1.1 x\n**Table 5: T**\n")
    assert "**Table 1: T**" in out


def test_drop_ungrounded_claims_removes_unsupported_number_sentence():
    from app.agent.report_postprocess import drop_ungrounded_claims

    text = "Accuracy reached 91.2% on MVTec [1]. Costs fell by 2.5x [1]. Plain claim [1]."
    out, dropped = drop_ungrounded_claims(text, "Result: 91.2 accuracy")
    assert "91.2%" in out
    assert "2.5x" not in out and len(dropped) == 1
    assert "Plain claim [1]." in out


def test_synthesize_blocks_when_no_citations():
    import pytest

    from app.agent.nodes.synthesize_node import InsufficientEvidenceError, synthesize_node

    with pytest.raises(InsufficientEvidenceError):
        synthesize_node({"question": "q", "citations": []})


def test_ambiguous_ref_resolved_by_sentence_overlap():
    text = (
        "**Table 4: Fusion strategies by combination stage**\n\n"
        "**Table 4: Quantitative comparison of published Dice results**\n\n"
        "The quantitative comparison of Dice results in Table 4 is not comparable across datasets.\n\n"
        "Fusion strategies by combination stage are listed in Table 4."
    )
    out, low = renumber_captions_report(text)
    assert "**Table 1: Fusion strategies" in out and "**Table 2: Quantitative comparison" in out
    assert "Dice results in Table 2 is not" in out
    assert "combination stage are listed in Table 1." in out
    assert low == []


def test_ambiguous_ref_without_overlap_is_reported_low_confidence():
    text = "**Figure 1: Alpha pipeline**\n\n**Figure 1: Omega curves**\n\nSee Figure 1 above."
    _, low = renumber_captions_report(text)
    assert low and "Figure 1" in low[0]


def test_cross_references_dangling_is_reported():
    text = "**Table 1: A**\n\n**Table 2: B**\n\nResults in Table 5 and Table 2.\n\nSee Figure 3."
    problems = check_cross_references(text)
    assert any("Table [5]" in p for p in problems)
    assert any("Figure [3]" in p for p in problems)


def test_cross_references_ignores_source_paper_tables_and_fences():
    text = "**Table 1: A**\n\nAs in Table 9 of [7] and Table 2 in the original paper.\n\n```table\n{\"caption\": \"see Table 8\"}\n```"
    assert check_cross_references(text) == []


def test_finalize_structure_report_returns_all_three():
    fixed, dangling, low = finalize_structure_report("**Table 3: A**\n\nSee Table 3 and Table 6.")
    assert "**Table 1: A**" in fixed and "Table 1 and Table 6" in fixed
    assert dangling and not low


def test_strip_dangling_inside_cluster_keeps_valid_marker():
    from app.agent.evidence.report_structure import strip_dangling_citations

    assert strip_dangling_citations("synthesis [7, 73].", 36) == ("synthesis [7].", [73])
    assert strip_dangling_citations("methods [73, 7] work", 36) == ("methods [7] work", [73])


def test_finalize_numbers_figures_by_block_and_drops_ghost_caption():
    from app.agent.evidence.report_structure import align_figure_captions

    chart = '```chart\n{"type": "dot"}\n```'
    text = (
        f"**Figure 5: A.** Desc A.\n\n{chart}\n\n"
        "**Figure 7: Scatter.** Ghost desc.\n\n"
        "The scatter plot (Figure 7) shows cost. Figure 5 shows A.\n\n"
        f"{chart}\n\n**Figure 8: B.**\n\n{chart}"
    )
    out, orphans = align_figure_captions(text)
    assert orphans == [7]
    assert "Ghost desc" not in out and "scatter plot" not in out
    assert "**Figure 1: A.**" in out and "Figure 1 shows A." in out
    assert "**Figure 3: B.**" in out  # khối thứ 2 (tự chèn, không chú thích) vẫn chiếm số 2
    fixed, dangling, _ = finalize_structure_report(out + "\n\nSee Figure 2.")
    assert dangling == []


def test_pdf_renderer_strips_figure_label_above_blocks_keeps_mermaid_title():
    from app.pipeline.export.pdf_renderer import _extract_blocks

    md = "**Figure 1: Taxonomy tree.** It shows axes.\n\n```mermaid\ngraph TD\nA-->B\n```\n\n**Figure 2: Img**\n\n```image\n{}\n```"
    body, blocks = _extract_blocks(md)
    assert "Figure 1" not in body and "Figure 2" not in body
    assert "It shows axes." in body
    assert 'data-caption="Taxonomy tree"' in blocks[0]


def test_panels_chart_renders_shared_legend_grid():
    from app.pipeline.export.chart_scientific import render_scientific_svg
    from app.pipeline.export.figure_layout import WIDE, chart_span

    panel = {"type": "line", "title": "JPEG", "labels": ["100", "75", "50"], "series": [{"name": "GAN", "values": [98, None, 85]}]}
    spec = {"type": "panels", "panels": [panel, {**panel, "type": "dot", "title": "Dot"}, {"type": "xyline", "title": "Blur",
            "series": [{"name": "Diffusion", "x": [0, 1, 2], "y": [97, 90, 80]}]}]}
    svg = render_scientific_svg(spec)
    assert svg.startswith("<svg") and chart_span(spec) == WIDE


def test_corpus_flow_is_honest_and_injected_once():
    from app.agent.evidence.corpus_flow import corpus_flow_block, inject_corpus_flow

    assert corpus_flow_block(40, 3, 5, 0) is None  # trích dẫn > truy xuất: số không nhất quán → không vẽ
    block = corpus_flow_block(40, 38, 35, 20)
    assert "(n = 40)" in block and "(n = 35)" in block and "(n = 20)" in block and "not a PRISMA" in block
    assert "review corpus" not in corpus_flow_block(None, 38, 35, 0)
    report = "## 2. Methods\n### 2.2 A\ntext\n### 2.3 B\n## 3. C"
    out = inject_corpus_flow(report, block)
    assert out.index("```mermaid") < out.index("### 2.3") and inject_corpus_flow(out, block) == out


def test_wide_td_taxonomy_becomes_lr():
    from app.agent.report_postprocess import orient_mermaid

    wide = "graph TD\n" + "\n".join(f'    A --> B{i}["Axis {i}"]\n    B{i} --> C{i}a\n    B{i} --> C{i}b' for i in range(6))
    assert orient_mermaid(wide).startswith("graph LR")
    assert orient_mermaid("flowchart TD\n  A --> B\n  A --> C").startswith("flowchart TD")


def test_timeline_years_must_match_references_and_render():
    import json

    from app.agent.report_postprocess import postprocess_report, reference_years
    from app.pipeline.export.chart_scientific import render_scientific_svg

    refs = ['[1] A et al., "X," *arXiv:2404.09556*, 2024.', '[2] B, "Y," *MICCAI*, 2016.', '[3] C, "Z," 2021.', '[4] D, "W," 2019.', "[5] no year"]
    years = reference_years(refs)
    assert years == {1: 2024, 2: 2016, 3: 2021, 4: 2019}
    events = [{"year": 2024, "label": "A [1]", "group": "SSM"}, {"year": 2016, "label": "B [2]", "group": "Latent"},
              {"year": 2021, "label": "C [3]", "group": "Transformer"}, {"year": 2019, "label": "D [4]", "group": "Latent"},
              {"year": 2015, "label": "Fake [3]", "group": "Latent"}, {"year": 2020, "label": "E [1, 2]", "group": "SSM"}]
    block = f'```chart\n{json.dumps({"type": "timeline", "events": events})}\n```'
    out = postprocess_report(block, "", None, None, "en", min_charts=0, ref_years=years)
    spec = json.loads(out.split("```chart\n")[1].split("\n```")[0])
    assert [e["label"] for e in spec["events"]] == ["A [1]", "B [2]", "C [3]", "D [4]"]  # năm sai / 2 trích dẫn → bỏ
    assert "```chart" not in postprocess_report(block, "", None, None, "en", min_charts=0)  # không có References → không tin
    assert render_scientific_svg(spec).startswith("<svg")
