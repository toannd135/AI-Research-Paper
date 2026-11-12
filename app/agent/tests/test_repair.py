"""Repair tất định sau Quality Gate: biểu đồ trộn vùng, điểm biểu đồ không truy vết được, câu ledger, paper chưa cite."""

import json
from types import SimpleNamespace

import pytest

from app.agent.evidence.consistency_check import check_ledger_claims
from app.agent.evidence.coverage import uncited_papers
from app.agent.evidence.quant_check import check_chart_block
from app.agent.evidence.repair import (
    CHART_NOTE,
    add_uncited_corpus,
    redact_untraced_chart_points,
    repair_chart_regions,
    repair_ledger_claims,
)
from app.agent.evidence.traceability import TRACED, UNTRACED, extract_numeric_claims

# Fixture BraTS/MRI: các kiểm tra ở đây thuộc chế độ MRI não (app/agent/domains.py)
pytestmark = pytest.mark.usefixtures("mri_domain")


def _chart(spec):
    return "```chart\n" + json.dumps(spec) + "\n```"


def _charts(text):
    return [json.loads(part.split("\n```")[0]) for part in text.split("```chart\n")[1:]]


def test_chart_regions_keeps_majority_series_region():
    spec = {
        "type": "bar",
        "caption": "Dice for WT, TC and ET on BraTS 2021 [1]",
        "labels": ["A", "B"],
        "series": [{"name": "Dice WT", "values": [90, 91]}, {"name": "Dice WT (ensemble)", "values": [92, 93]}, {"name": "Dice TC", "values": [85, 86]}],
    }
    out, fixed = repair_chart_regions("intro\n" + _chart(spec) + "\noutro")
    new = _charts(out)[0]
    assert fixed == [{"region_kept": "WT"}]
    assert [s["values"] for s in new["series"]] == [[90, 91], [92, 93]]
    assert "Only the whole tumor (WT) region is shown." in new["caption"]
    assert "TC" not in new["caption"] and "ET" not in new["caption"]
    assert check_chart_block(json.dumps(new)) == []
    assert out.count("```chart") == 1


def test_chart_regions_tie_prefers_wt_order_and_labels_path():
    spec = {"caption": "Dice per region [2]", "labels": ["TC", "ET", "Mean"], "series": [{"name": "nnU-Net", "values": [85, 80, 82], "errors": [1, 2, 3]}]}
    spec["caption"] = "Dice for TC and ET [2]"
    out, fixed = repair_chart_regions(_chart(spec))
    new = _charts(out)[0]
    assert fixed == [{"region_kept": "TC"}]
    assert new["labels"] == ["TC", "Mean"]
    assert new["series"][0]["values"] == [85, 82] and new["series"][0]["errors"] == [1, 3]


def test_chart_regions_leaves_single_region_and_bad_json():
    ok = _chart({"caption": "Dice on WT [1]", "labels": ["A"], "series": [{"name": "WT", "values": [1]}]})
    bad = "```chart\n{not json, WT TC}\n```"
    assert repair_chart_regions(ok + "\n" + bad) == (ok + "\n" + bad, [])


def _rec(block, location, value, status=UNTRACED):
    return {"block": block, "location": location, "value": value, "cites": [1], "status": status}


def test_redact_chart_points_nulls_value_and_counts_tables():
    table = "```table\n" + json.dumps({"caption": "T [1]", "columns": ["M", "Dice"], "rows": [["a [1]", "88.5"]]}) + "\n```"
    chart = _chart({"caption": "C [1]", "labels": ["x", "y"], "series": [{"name": "s1", "values": [1.5, 2.5]}, {"name": "s2", "values": [3.5, 4.5]}]})
    text = table + "\n\n" + chart
    assert [c["block"] for c in extract_numeric_claims(text)][-1] == "chart#2"
    records = [_rec("chart#2", "series 1, point 2", "2.5"), _rec("chart#2", "series 2, point 1", "3.5", TRACED)]
    out, removed = redact_untraced_chart_points(text, records)
    new = _charts(out)[0]
    assert new["series"][0]["values"] == [1.5, None] and new["series"][1]["values"] == [3.5, 4.5]
    assert CHART_NOTE.strip() in new["caption"]
    assert len(removed) == 1 and out.startswith(table)


def test_redact_chart_drops_all_null_series_and_empty_chart_renumbers_figures():
    c1 = _chart({"caption": "First [1]", "labels": ["x"], "series": [{"name": "a", "values": [7.25]}]})
    c2 = _chart({"caption": "Second [1]", "labels": ["x"], "series": [{"name": "b", "values": [1.0]}, {"name": "c", "values": [2.0]}]})
    c3 = _chart({"caption": "Third [1]", "labels": ["x"], "series": [{"name": "d", "values": [3.0]}]})
    text = f"See Figure 1 here. Figure 3 shows more.\n\n**Figure 1: First.**\n{c1}\n\nText.\n\n{c2}\n\n{c3}\n"
    records = [_rec("chart#1", "series 1, point 1", "7.25"), _rec("chart#2", "series 1, point 1", "1.0")]
    out, removed = redact_untraced_chart_points(text, records)
    assert len(removed) == 2
    assert "A chart planned" not in out and "**Figure 1: First.**" not in out
    assert "See Figure 1 here." not in out and "Figure 2 shows more." in out
    charts = _charts(out)
    assert len(charts) == 2 and [s["name"] for s in charts[0]["series"]] == ["c"]


def test_repair_ledger_claims_removes_phrase_and_passes_check():
    text = (
        "Intro. The ledger contains verified records for full-modality, missing-modality configurations and cross-dataset settings. "
        "Records also cover missing-modality settings. Other text.\n\n## References\n\n[1] missing-modality records ledger."
    )
    assert check_ledger_claims(text, 0)
    out, fixed = repair_ledger_claims(text, 0)
    assert len(fixed) == 2
    assert check_ledger_claims(out, 0) == []
    assert "full-modality and cross-dataset settings." in out
    assert out.endswith("[1] missing-modality records ledger.")
    assert repair_ledger_claims(text, 2) == (text, [])


def test_add_uncited_corpus_inserts_titles_with_first_index():
    citations = [SimpleNamespace(paper_id=p) for p in ("p1", "p2", "p2", "p3")]
    catalog = {"p2": {"title": "Second paper."}, "p3": {"title": "Third paper"}}
    text = "## 1. Introduction\n\nA [1].\n\n## 2. Related Work\n\nB [1].\n\n## 3. Methods\n\nC."
    out, missing = add_uncited_corpus(text, citations, catalog)
    assert missing == ["p2", "p3"]
    assert "*Second paper* [2]; *Third paper* [4]." in out
    assert out.index("Additional corpus studies") < out.index("## 3. Methods") and out.index("Additional corpus studies") > out.index("B [1]")
    assert uncited_papers(citations, out) == []
    assert add_uncited_corpus(out, citations, catalog) == (out, [])


def test_add_uncited_corpus_falls_back_to_references_or_end():
    citations = [SimpleNamespace(paper_id="p1"), SimpleNamespace(paper_id="p2")]
    out, _ = add_uncited_corpus("Body [1].\n\n## References\n\n[1] x", citations, {})
    assert out.index("*untitled corpus document* [2]") < out.index("## References")
    out2, _ = add_uncited_corpus("Body [1].", citations, {"p2": {"title": "T"}})
    assert out2.rstrip().endswith("*T* [2].")


def test_redact_two_empty_charts_keeps_surviving_figure_label_and_sentence():
    c1 = _chart({"caption": "One [1]", "labels": ["x"], "series": [{"name": "a", "values": [1.25]}]})
    c2 = _chart({"caption": "Two [1]", "labels": ["x"], "series": [{"name": "b", "values": [2.0]}]})
    c3 = _chart({"caption": "Three [1]", "labels": ["x"], "series": [{"name": "c", "values": [3.75]}]})
    text = (
        f"As Figure 3 illustrates, things change. Figure 2 is kept.\n\n**Figure 1: Gone**\n{c1}\n\n"
        f"**Figure 2: Kept**\n{c2}\n\n**Figure 3: Also gone**\n{c3}\n"
    )
    records = [_rec("chart#1", "series 1, point 1", "1.25"), _rec("chart#3", "series 1, point 1", "3.75")]
    out, removed = redact_untraced_chart_points(text, records)
    assert len(removed) == 2 and "A chart planned" not in out
    assert "**Figure 1: Kept**" in out and "Figure 1 is kept." in out
    assert "As Figure 3 illustrates" not in out and "Figure 2" not in out
    assert "Gone" not in out and "Also gone" not in out


def test_repair_ledger_claims_keeps_headings_tables_code_and_hard_breaks():
    text = (
        "## 4. Missing-modality results in the ledger\n\n"
        "| Ledger | missing-modality configurations |\n"
        "Line one.  \nThe ledger has records for full-modality, missing-modality configurations and cross-dataset settings.\n\n"
        "```python\nx  =  1  # ledger missing-modality configurations\n```\n\nEnd.\n\n## References\n\n[1] x"
    )
    out, fixed = repair_ledger_claims(text, 0)
    assert len(fixed) == 1
    assert out.startswith("## 4. Missing-modality results in the ledger\n")
    assert "| Ledger | missing-modality configurations |" in out
    assert "```python\nx  =  1  # ledger missing-modality configurations\n```" in out
    assert "Line one.  \n" in out
    assert "full-modality and cross-dataset settings." in out


def test_chart_regions_rewrites_region_count_in_caption():
    spec = {
        "caption": "Dice for three tumor sub-regions across WT, TC and ET [1]",
        "labels": ["A"],
        "series": [{"name": "Dice WT", "values": [90]}, {"name": "Dice WT (b)", "values": [91]}, {"name": "Dice ET", "values": [80]}],
    }
    out, fixed = repair_chart_regions(_chart(spec))
    cap = _charts(out)[0]["caption"]
    assert fixed == [{"region_kept": "WT"}]
    assert "three" not in cap.lower() and "sub-regions" not in cap and "regions" not in cap
    assert "TC" not in cap and "ET" not in cap


def test_add_uncited_corpus_counts_cluster_and_located_citations():
    citations = [SimpleNamespace(paper_id=p) for p in ("p1", "p2", "p3", "p4")]
    out, missing = add_uncited_corpus("X [1, 2] and Y [3–3]; see [4, Table 1].", citations, {})
    assert missing == [] and out == "X [1, 2] and Y [3–3]; see [4, Table 1]."


def test_soften_promotional_claims_only_in_abstract_and_conclusion():
    from app.agent.evidence.repair import soften_promotional_claims

    text = (
        "## Abstract\n\nThe framework jointly classifies methods, replacing the single-axis frameworks of prior surveys [3]. "
        "It provides a rigorous, evidence-grounded foundation for reproducible and clinically reliable segmentation.\n\n"
        "## 2. Methods\n\nWe use a rigorous protocol.\n\n## 7. Conclusion\n\nThis is an unprecedented, unified view.\n"
    )
    out, changed = soften_promotional_claims(text)
    assert "complementing the single-axis frameworks of prior surveys [3]" in out
    assert "provides an evidence-grounded foundation for reproducible and clinically relevant segmentation." in out
    assert "We use a rigorous protocol." in out  # thân bài không bị đụng
    assert "This is a unified view." in out
    assert len(changed) == 2


def test_drop_duplicate_charts_keeps_first_and_renumbers():
    from app.agent.evidence.repair import drop_duplicate_charts

    pts = {"x": [1.0, 2.0, 3.0, 4.0, 5.0], "y": [0.8, 0.81, 0.82, 0.83, 0.84]}
    a = _chart({"type": "scatter", "caption": "A [1]", "series": [{"name": "all", **pts}]})
    b = _chart({"type": "scatter", "caption": "B [1]", "series": [{"name": f"m{i}", "x": [x], "y": [y]} for i, (x, y) in enumerate(zip(pts["x"], pts["y"], strict=True))]})
    c = _chart({"type": "scatter", "caption": "C [2]", "series": [{"name": "other", "x": [1, 2, 3, 4], "y": [9, 8, 7, 6]}]})
    text = f"Figure 1 shows A. Figure 2 shows B. Figure 3 shows C.\n\n{a}\n\n**Figure 2: B.**\n{b}\n\n{c}\n"
    out, dropped = drop_duplicate_charts(text)
    assert dropped == [2]
    assert len(_charts(out)) == 2 and "**Figure 2: B.**" not in out
    assert "Figure 1 shows A. Figure 2 shows C." in out
