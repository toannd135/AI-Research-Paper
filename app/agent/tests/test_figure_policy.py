"""Chart Selection Policy và Figure Layout cho PDF hai cột."""

import json

import pytest

from app.agent.evidence.figure_policy import figure_policy_warnings, refine_chart_spec
from app.pipeline.export.figure_layout import COLUMN, WIDE, chart_span, chart_width, mermaid_span


def _bar(names, labels=("WT", "TC", "ET")):
    return {
        "type": "bar",
        "labels": list(labels),
        "series": [{"name": n, "values": [80.0 + i for i in range(len(labels))]} for n in names],
    }


@pytest.mark.parametrize(
    "names",
    [
        ("Validation", "Testing"),
        ("With multi-view fusion", "Without multi-view fusion"),
        ("Full modalities", "Missing FLAIR"),
        ("Internal test", "External test"),
    ],
)
def test_paired_conditions_become_dumbbell(names):
    spec, reason = refine_chart_spec(_bar(names))
    assert spec["type"] == "dumbbell" and reason
    assert spec["series"] == _bar(names)["series"]  # chỉ đổi cách vẽ, giữ nguyên số


def test_methods_by_regions_become_dot_plot():
    spec, _ = refine_chart_spec(_bar(["WT", "TC", "ET"], labels=("Swin UNETR", "nnU-Net", "SegResNet", "TransBTS")))
    assert spec["type"] == "dot"


def test_simple_bar_and_error_bars_are_kept():
    single = _bar(["Dice"])
    assert refine_chart_spec(single) == (single, None)
    with_err = _bar(["A", "B", "C"])
    with_err["series"][0]["errors"] = [1, 1, 1]
    assert refine_chart_spec(with_err)[1] is None


def _fence(kind, spec):
    return f"```{kind}\n{json.dumps(spec)}\n```\n"


def test_warnings_for_too_many_bars_duplicates_and_table_repeats():
    table = {"columns": ["M", "WT"], "rows": [["A", "80.0"], ["B", "81.0"], ["C", "82.0"], ["D", "83.0"]]}
    bar = {
        "type": "bar",
        "labels": ["A", "B", "C", "D"],
        "series": [{"name": "WT", "values": [80.0, 81.0, 82.0, 83.0]}],
    }
    text = _fence("table", table) + _fence("chart", bar) * 3
    warnings = figure_policy_warnings(text)
    assert any("3 biểu đồ cột" in w for w in warnings)
    assert any("cùng dữ liệu" in w for w in warnings)
    assert any("lặp lại số của một bảng" in w for w in warnings)
    assert figure_policy_warnings(_fence("chart", {**bar, "derived": True})) == []


def test_figures_default_to_one_column():
    assert chart_span(_bar(["WT"])) == COLUMN and chart_width(_bar(["WT"])) < 4
    assert chart_span({"type": "dumbbell", "labels": ["WT", "TC", "ET"]}) == COLUMN
    assert chart_span({"type": "heatmap", "x_labels": ["A", "B", "C"]}) == COLUMN


def test_wide_only_when_needed_or_requested():
    crowded = _bar([f"S{i}" for i in range(4)], labels=[f"Method number {i}" for i in range(5)])
    assert chart_span(crowded) == WIDE
    assert chart_span({"type": "heatmap", "x_labels": [f"[{i}]" for i in range(30)]}) == WIDE
    assert chart_span({**crowded, "layout": "column"}) == COLUMN
    assert chart_span({**_bar(["WT"]), "layout": "wide"}) == WIDE


def test_mermaid_span():
    assert mermaid_span('graph TD\nA["x"] --> B["y"]\nB --> C["z"]') == COLUMN
    lr = "graph LR\n" + "\n".join(f'N{i}["n{i}"] --> N{i + 1}["n{i + 1}"]' for i in range(6))
    assert mermaid_span(lr) == WIDE


def test_metric_axis_label_moves_to_horizontal_axis():
    spec, _ = refine_chart_spec({**_bar(["Validation", "Testing"]), "y_label": "Dice (ratio)", "x_label": "Region"})
    assert spec["x_label"] == "Dice (ratio)" and "y_label" not in spec
