import json

from app.agent.report_postprocess import (
    build_ledger_chart,
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
