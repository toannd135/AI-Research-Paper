from app.agent.evidence.display_check import check_display_items

_TABLE = '```table\n{"columns": ["A"], "rows": [["1"]]}\n```'
_CHART = '```chart\n{"type": "heatmap", "x_labels": [], "y_labels": [], "matrix": []}\n```'
_MERMAID = "```mermaid\ngraph TD\n A-->B\n```"


def test_thin_survey_warns_but_does_not_invent():
    res = check_display_items(f"Text.\n\n{_MERMAID}\n\n{_TABLE}\n", "review")
    assert res["counts"] == {"figures": 1, "tables": 1}
    assert any("Figure" in w and "thấp hơn" in w for w in res["warnings"])
    assert any("Table" in w and "thấp hơn" in w for w in res["warnings"])


def test_counts_markdown_tables_and_chart_types():
    md = "| a | b |\n|---|---|\n| 1 | 2 |\n"
    res = check_display_items(f"{md}\n{_TABLE}\n{_CHART}\n", "review")
    assert res["counts"]["tables"] == 2
    assert res["chart_types"] == ["heatmap"]


def test_dangling_and_unmentioned_references():
    res = check_display_items(f"See Figure 3 and Table 1.\n\n{_MERMAID}\n\n{_CHART}\n{_TABLE}\n", "review")
    assert any("[3]" in w and "Figure" in w for w in res["warnings"])
    assert any("chỉ 1 số được nhắc" in w for w in res["warnings"])


def test_target_by_paper_type_and_in_range_no_count_warning():
    text = "\n".join([_MERMAID] * 4 + [_TABLE] * 3) + "\nFigure 1 Figure 2 Figure 3 Figure 4 Table 1 Table 2 Table 3"
    res = check_display_items(text, "original_research")
    assert res["target"]["figures"] == (4, 7)
    assert res["warnings"] == []
