from app.agent.evidence.report_structure import (
    check_cross_references,
    finalize_structure,
    finalize_structure_report,
    rematch_refs_by_caption,
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


def test_big_taxonomy_tree_compacts_leaves_per_axis():
    from app.agent.report_postprocess import orient_mermaid, validate_mermaid

    tree = "graph TD\n" + "\n".join(
        f'    R["Root"] --> X{i}["Axis {i}"]\n' + "\n".join(f'    X{i} --> L{i}{j}["Leaf {i}.{j}<br/>[{j + 1}]"]' for j in range(3)) for i in range(6)
    )
    out = orient_mermaid(tree)
    assert out.startswith("graph LR") and validate_mermaid(out) == []
    assert '"• Leaf 0.0 [1]<br/>• Leaf 0.1 [2]<br/>• Leaf 0.2 [3]"' in out and "L00" not in out


def test_image_caption_with_source_tag_is_used_as_figcaption(tmp_path, monkeypatch):
    from app.pipeline.export.pdf_renderer import _number_figures_and_tables

    body = '<figure class="fig photo" data-kind="figure" data-caption="Arch overview <i>Source: [3]</i>"><img>__CAPTION__</figure>'
    out = _number_figures_and_tables("<h3>5.3 Qualitative</h3>" + body)
    assert "<b>Figure 1.</b> Arch overview <i>Source: [3]</i>" in out


def test_strip_dangling_located_citation():
    from app.agent.evidence.report_structure import strip_dangling_citations

    out, removed = strip_dangling_citations("As in [52, Table 1]. Also [3, 52, p. 4] and [2].", 45)
    assert out == "As in. Also [3, p. 4] and [2]."
    assert removed == [52, 52]


def test_rematch_table_and_figure_refs_by_caption_keyword():
    import json

    from app.agent.evidence.report_structure import finalize_structure_report

    chart = "```chart\n" + json.dumps({"caption": "Dice trend over years", "labels": ["a"], "series": [{"name": "s", "values": [1]}]}) + "\n```"
    mermaid = "```mermaid\ngraph TD\nA-->B\n```"
    text = (
        "We organise methods with a six-axis taxonomy (Table 1). Table 2 lists datasets. Figure 1 presents a taxonomy-tree of methods.\n\n"
        "**Table 1: Benchmark Dice on BraTS.**\n\n| a |\n\n**Table 2: Public datasets.**\n\n| b |\n\n"
        "**Table 3: Six-axis taxonomy of segmentation methods.**\n\n| c |\n\n"
        f"{chart}\n\n**Figure 2: Taxonomy tree of methods.**\n{mermaid}\n"
    )
    fixed, dangling, _ = finalize_structure_report(text)
    assert "six-axis taxonomy (Table 3)" in fixed
    assert "Table 2 lists datasets" in fixed
    assert "Figure 2 presents a taxonomy-tree" in fixed
    assert dangling == []


def _fig_chart(caption):
    import json

    return "```chart\n" + json.dumps({"caption": caption, "labels": ["a"], "series": [{"name": "s", "values": [1]}]}) + "\n```"


def test_located_cite_regex_ignores_math_intervals():
    text = "Coordinates clipped to [0, L] and windows [0, T] as in [3, 5], [3–5] and [3, p. 4]."
    out, removed = strip_dangling_citations(text, 5)
    assert removed == []
    assert "clipped to [0, L] and windows [0, T]" in out and "[3], [5]" in out and out.endswith("and [3, p. 4].")
    out, removed = strip_dangling_citations("Values in [0, L] from [9, Table 2].", 5)
    assert out == "Values in [0, L] from." and removed == [9]


def test_strip_dangling_citations_inside_chart_caption_json():
    import json

    block = "```chart\n" + json.dumps({"caption": "Dice [52, Table 1] and [2]", "labels": ["a [1]"], "series": []}) + "\n```"
    out, removed = strip_dangling_citations("Text [1].\n\n" + block + "\n", 5)
    spec = json.loads(out.split("```chart\n")[1].split("\n```")[0])
    assert removed == [52]
    assert spec["caption"] == "Dice and [2]" and spec["labels"] == ["a [1]"]
    code = "```python\nx = a[52]\n```"
    assert strip_dangling_citations(code, 5) == (code, [])


def _two_tables(body):
    return (
        "**Table 1: Segmentation networks architectures**\n\n| a |\n\n**Table 2: Public datasets**\n\n| b |\n\n" + body
    )


def test_rematch_skips_multi_ref_sentences_source_tables_and_brackets():
    for body in (
        "Table 1 lists segmentation networks while Table 2 lists datasets.",
        "Public datasets appear in the original study [3, Table 1] for benchmark.",
        "Table 1 of the Draft Basis reports public datasets.",
        "Table 1 of [3] reports public datasets.",
    ):
        text = _two_tables(body)
        assert rematch_refs_by_caption(text) == (text, []), body


def test_rematch_fixes_inline_bold_figure_reference():
    text = (
        "**Figure 1** presents a taxonomy-tree of approaches.\n\n**Figure 1: Dice comparison of networks**\n"
        + _fig_chart("Dice comparison")
        + "\n\n**Figure 2: Taxonomy tree of approaches**\n"
        + _fig_chart("Taxonomy tree")
        + "\n"
    )
    out, changes = rematch_refs_by_caption(text)
    assert changes == ["Figure 1 -> Figure 2"]
    assert out.startswith("**Figure 2** presents a taxonomy-tree")


def test_renumber_sections_updates_section_references():
    text = (
        "## 1. Intro\n\nSection 7 concludes and Section 6.2 details it; see §4 and Section 9.\n\n"
        "## 2. A\n\n## 3. B\n\n## 4. C\n\n## 6. D\n\n### 6.1 First\n\n### 6.2 Sub\n\n## 7. Conclusion\n\nx\n\n"
        "```python\n# Section 7\n```\n\n## References\n\n[1] Section 7 of a book."
    )
    out = renumber_sections(text)
    assert "Section 6 concludes and Section 5.2 details it; see §4 and Section 9." in out
    assert "## 5. D" in out and "### 5.2 Sub" in out and "## 6. Conclusion" in out
    assert "```python\n# Section 7\n```" in out and out.endswith("[1] Section 7 of a book.")


def test_strip_dangling_citations_cleans_mermaid_labels():
    text = '```mermaid\ngraph LR\n  Y1[2019]\n  A["Late<br/>[5, 53]"]\n  B["Synthesis<br/>[47]"]\n```\n'
    out, removed = strip_dangling_citations(text, 45)
    assert '"Late<br/>[5]"' in out
    assert '"Synthesis"' in out
    assert "Y1[2019]" in out
    assert sorted(removed) == [47, 53]


def test_rebuild_paper_organization_from_real_headings():
    from app.agent.evidence.report_structure import rebuild_paper_organization

    text = (
        "## 1. Introduction\n\n### 1.2 Paper Organization\n\nSection 2 formalizes the taxonomy. Section 6 summarizes the ledger.\n\n"
        "## 2. Review Methodology\n\nx\n\n## 3. Taxonomy\n\ny\n\n## 4. Conclusion\n\nz\n\n## References\n\n[1] a\n"
    )
    out, changed = rebuild_paper_organization(text)
    assert changed
    assert "Section 6" not in out
    assert "Section 2 presents Review Methodology; Section 3 presents Taxonomy; and Section 4 concludes the paper." in out
    assert "## 2. Review Methodology" in out


def test_fix_internal_draft_refs():
    from app.agent.evidence.report_structure import fix_internal_draft_refs

    text = (
        "## 1. Introduction\n\nGaps structure the Discussion (Section 5 of the full manuscript) and D1-D6.\n"
        "The table (Section 5 of the full manuscript) lists them. Synthesis (§1.3, §5.4 of the Draft Basis) shows gaps.\n\n"
        "## 2. Discussion & Open Challenges\n\nw\n"
    )
    out, changes = fix_internal_draft_refs(text)
    assert "the Discussion (Section 2) and" in out
    assert "The table lists them." in out
    assert "Draft Basis" not in out and "full manuscript" not in out
    assert len(changes) == 3


def test_fix_internal_draft_refs_source_tables_and_render_meta():
    from app.agent.evidence.report_structure import fix_internal_draft_refs

    text = (
        "## 3. Taxonomy\n\n**Efficiency.** Table 1 of the Draft Basis reports parameters [45]. As shown in Table 1 of the full manuscript, x.\n"
        "Figure 2 presents the tree. The tree is rendered left-to-right (graph LR) to keep labels readable.\n"
    )
    out, _ = fix_internal_draft_refs(text)
    assert "**Efficiency.** The corresponding source table reports parameters [45]." in out
    assert "As shown in the corresponding source table, x." in out
    assert out.rstrip().endswith("Figure 2 presents the tree.")


def test_timeline_year_ticks_do_not_crowd_narrow_axis():
    from app.pipeline.export.chart_scientific import _spaced_years

    years = [2018, 2021, 2022, 2023, 2024]
    assert _spaced_years(years, 2017.3, 2024.7, 2.0) == [2018, 2021, 2024]  # khung một cột: bỏ năm quá sát
    assert _spaced_years(years, 2017.3, 2024.7, 6.0) == years  # khung cả trang: đủ chỗ cho mọi năm


def test_corpus_flow_is_horizontal_with_short_labels():
    from app.agent.evidence.corpus_flow import corpus_flow_block, inject_corpus_flow

    block = corpus_flow_block(52, 52, 45, 12)
    assert "flowchart LR" in block and "Cited in this review (n = 45)" in block
    legacy = "## 2. M\n**Figure 1: x**\n\n```mermaid\nflowchart TD\n  C[\"Papers cited in this review (n = 45)\"]\n```\n### 2.3 B\n"
    assert inject_corpus_flow(legacy, block) == legacy  # bài cũ đã có sơ đồ: không chèn lần hai


def test_render_meta_sentence_after_bold_figure_lead_is_removed():
    from app.agent.evidence.report_structure import fix_internal_draft_refs

    text = "## 3. T\n**Figure 2** presents the tree. It is rendered left-to-right (`graph LR`) for readability.\n**Figure 2: Tree (graph LR).**\n"
    out, changes = fix_internal_draft_refs(text)
    assert "**Figure 2** presents the tree." in out and "rendered left-to-right" not in out
    assert "**Figure 2: Tree (graph LR).**" in out and changes
