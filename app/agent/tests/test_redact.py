"""Gỡ ô số không truy vết được khỏi bảng bản cuối."""

import json
from types import SimpleNamespace

from app.agent.evidence.quality_gate import trace_text_records
from app.agent.evidence.redact import CAPTION_NOTE, REDACTED, redact_untraced_cells


def _chunk(pid, text):
    return SimpleNamespace(chunk=SimpleNamespace(paper_id=pid, page=1, text=text))


def _state():
    return {"citations": [SimpleNamespace(paper_id="p1")], "evidence": [_chunk("p1", "Dice 88.5 and HD95 4.2")]}


def _table(rows, **extra):
    spec = {"caption": "Results", "columns": ["Method [Ref]", "Dice", "HD95"], "rows": rows, **extra}
    return "intro\n```table\n" + json.dumps(spec) + "\n```\noutro"


def _spec(text):
    return json.loads(text.split("```table\n")[1].split("\n```")[0])


def test_untraced_cell_becomes_nr_and_caption_defines_it():
    text = _table([["A [1]", "88.5", "6.855"]])
    fixed, removed = redact_untraced_cells(text, trace_text_records(_state(), text))
    spec = _spec(fixed)
    assert spec["rows"][0] == ["A [1]", "88.5", REDACTED]  # 88.5 có trong nguồn nên giữ
    assert CAPTION_NOTE.strip() in spec["caption"]
    assert [r["value"] for r in removed] == ["6.855"]


def test_nothing_changes_when_every_value_is_traced():
    text = _table([["A [1]", "88.5", "4.2"]])
    fixed, removed = redact_untraced_cells(text, trace_text_records(_state(), text))
    assert fixed == text and removed == []


def test_derived_tables_and_years_are_left_alone():
    text = _table([["A [1] (2021)", "1.0", "2.0"]], derived=True)
    fixed, removed = redact_untraced_cells(text, trace_text_records(_state(), text))
    assert fixed == text and removed == []


def test_second_block_is_addressed_by_its_own_index():
    first = _table([["A [1]", "88.5", "4.2"]])
    second = _table([["B [1]", "11.1", "4.2"]])
    text = first + "\n\n" + second
    fixed, removed = redact_untraced_cells(text, trace_text_records(_state(), text))
    assert [r["block"] for r in removed] == ["table#2"]
    assert fixed.count(REDACTED) >= 1 and '"88.5"' in fixed  # bảng 1 nguyên vẹn


def test_caption_note_is_not_duplicated_on_repeat():
    text = _table([["A [1]", "99.9", "4.2"]])
    once, _ = redact_untraced_cells(text, trace_text_records(_state(), text))
    again, removed = redact_untraced_cells(once, trace_text_records(_state(), once))
    assert removed == [] and again == once and once.count("withdrawn") == 1


def test_verify_final_report_redacts_then_regates_on_the_shipped_text():
    from app.agent.nodes.synthesize_node import _verify_final_report

    state = _state()
    text = _table([["A [1]", "88.5", "6.855"]])
    draft_gate = {"passed": False, "blocking": ["x", "y"], "warnings": ["w"]}

    report, validation = _verify_final_report(state, text, state["citations"], draft_gate, [], ["cảnh báo cấu trúc"])

    assert REDACTED in report and "6.855" not in report
    assert validation["draft_gate"] == {"passed": False, "blocking": 2, "warnings": 1}
    assert [c["value"] for c in validation["redacted_cells"]] == ["6.855"]
    assert validation["traceability"]["counts"]["UNTRACED"] == 0  # gate cuối thấy bản đã gỡ
    assert "cảnh báo cấu trúc" in validation["warnings"]
