import json
import re

from app.agent.report_postprocess import (
    build_ledger_chart,
    build_ledger_charts,
    fix_mermaid_block,
    postprocess_report,
    scrub_chart_spec,
    scrub_table_spec,
    validate_mermaid,
)

_DRAFT = """analysis
## Quantitative Evidence Ledger
| Source [n] | Method | Dataset | Metric | Value | Notes |
|---|---|---|---|---|---|
| [1] | A | D1 | F1 | 90.1 | x |
| [2] | B | D1 | F1 | 85.3 | x |
| [3] | C | D1 | F1 | 70.2 | x |
"""


class _Fake:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def generate(self, messages, model_name=None):
        from app.ai.llm_gateway.base import LLMResponse

        self.calls += 1
        return LLMResponse(text=self.text, model="fake")


def test_validate_mermaid_detects_problems():
    assert validate_mermaid('graph TD\n A["x"] --> B["y"]') == []
    assert validate_mermaid("hello world")
    assert validate_mermaid('graph TD\n subgraph S\n A["x"] --> B["y"]')
    assert validate_mermaid('graph TD\n A["x --> B["y"]')


def test_fix_mermaid_uses_llm_then_drops():
    bad = 'graph TD\n A["x --> B'
    good = 'graph TD\n A["x"] --> B["y"]'
    assert fix_mermaid_block(bad, _Fake(good), None) is not None
    assert fix_mermaid_block(bad, _Fake(bad), None) is None
    assert fix_mermaid_block(bad, None, None) is None


def test_scrub_table_replaces_ungrounded_numbers():
    body = json.dumps({"columns": ["Method", "F1"], "rows": [["A [1]", "90.1"], ["B [2]", "99.9"]]})
    out = json.loads(scrub_table_spec(body, _DRAFT))
    assert out["rows"] == [["A [1]", "90.1"], ["B [2]", "–"]]
    assert scrub_table_spec("not json", _DRAFT) is None


def test_scrub_chart_drops_invented_values():
    body = json.dumps({"labels": ["A", "B", "C"], "series": [{"name": "F1", "values": [90.1, 12.3, 70.2]}]})
    out = json.loads(scrub_chart_spec(body, _DRAFT))
    assert out["series"][0]["values"] == [90.1, None, 70.2]
    assert scrub_chart_spec(json.dumps({"labels": ["A"], "series": [{"values": [5.5]}]}), _DRAFT) is None


def test_ledger_chart_built_from_real_values():
    spec = json.loads(build_ledger_chart(_DRAFT))
    assert spec["labels"] == ["A", "B", "C"]
    assert spec["series"][0]["values"] == [90.1, 85.3, 70.2]
    assert build_ledger_chart("no ledger here") is None


def test_postprocess_injects_chart_and_translates():
    report = "## 4. Experiments\n\nText.\n\nChúng tôi đã thực nghiệm trên nhiều tập dữ liệu khác nhau.\n\n## 5. Discussion\n\nDone."
    out = postprocess_report(report, _DRAFT, _Fake("We experimented on many datasets."), None, "en")
    assert "```chart" in out and out.index("```chart") < out.index("## 5.")
    assert "Chúng tôi" not in out and "We experimented" in out


def test_postprocess_keeps_target_language_and_translates_english_into_it():
    report = (
        "## 4. Thực nghiệm\n\nChúng tôi đánh giá phương pháp trên nhiều tập dữ liệu khác nhau và so sánh kết quả với các baseline.\n\n"
        "This paragraph is written entirely in English and clearly does not belong in a Vietnamese manuscript at all.\n\n## 5. Thảo luận"
    )
    fake = _Fake("Đoạn này đã được dịch hoàn toàn sang tiếng Việt để bài báo thống nhất về ngôn ngữ cho người đọc.")
    out = postprocess_report(report, "", fake, None, "vi")
    assert "entirely in English" not in out and "đã được dịch" in out and fake.calls == 1


def test_scrub_chart_spec_keeps_grounded_scientific_charts():
    draft = "loss 0.9 0.5 0.3 and dice 90.1 85.2"
    xy = json.loads(scrub_chart_spec(json.dumps({"type": "xyline", "series": [{"name": "T", "x": [1, 2, 3, 4], "y": [0.9, 0.5, 0.3, 0.1]}]}), draft))
    assert xy["series"][0]["y"] == [0.9, 0.5, 0.3]  # 0.1 không có căn cứ → bỏ điểm
    assert xy["series"][0]["x"] == [1, 2, 3]
    heat = json.loads(scrub_chart_spec(json.dumps({"type": "heatmap", "x_labels": ["a", "b"], "y_labels": ["c"], "matrix": [[90.1, 85.2]]}), draft))
    assert heat["matrix"] == [[90.1, 85.2]]
    box = json.loads(scrub_chart_spec(json.dumps({"type": "boxplot", "series": [{"name": "s", "samples": [0.9, 0.5, 7.7]}]}), draft))
    assert box["series"][0]["samples"] == [0.9, 0.5]


def test_scrub_chart_spec_drops_scientific_chart_without_grounded_values():
    assert scrub_chart_spec(json.dumps({"type": "xyline", "series": [{"name": "T", "x": [1, 2], "y": [0.77, 0.66]}]}), "0.9") is None


_DRAFT3 = """analysis
## Quantitative Evidence Ledger
| Source [n] | Method | Dataset | Metric | Value | Notes |
|---|---|---|---|---|---|
""" + "".join(
    f"| [{i}] | M{i} | BraTS2020 | Dice {r} | {80 + i + k} | x |\n"
    for r, k in (("WT", 8), ("TC", 3), ("ET", 0))
    for i in (1, 2, 3)
)


def test_ledger_charts_one_per_setting_and_min_charts_injected():
    charts = build_ledger_charts(_DRAFT3, 3)
    assert len(charts) == 3
    assert {json.loads(c)["type"] for c in charts} == {"barh", "bar", "heatmap"}
    out = postprocess_report("## 4. X\n\nText.\n\n## 5. Y\n\nDone.", _DRAFT3, None, None, "en", min_charts=3)
    assert out.count("```chart") == 3
    assert {json.loads(m)["type"] for m in re.findall(r"```chart\n(.*?)\n```", out, re.DOTALL)} == {"barh", "bar", "heatmap"}
    assert out.index("```chart") < out.index("## 5.")


def test_min_charts_not_fabricated_when_ledger_thin():
    out = postprocess_report("## 4. X\n\n## 5. Y\n\nDone.", _DRAFT, None, None, "en", min_charts=3)
    assert out.count("```chart") == 1
