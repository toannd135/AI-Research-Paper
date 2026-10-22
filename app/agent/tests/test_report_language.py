"""Chuẩn hoá ngôn ngữ: tiêu đề, bảng, khối JSON và mermaid cũng được dịch, có kiểm tra cấu trúc."""

import json

from app.agent.report_postprocess import translate_foreign_paragraphs


class _Resp:
    def __init__(self, text):
        self.text = text


class FakeGateway:
    """Trả bản 'dịch' theo từ điển; ghi lại số lần gọi."""

    def __init__(self, table):
        self.table, self.calls = table, 0

    def generate(self, messages, model_name=None, **_):
        self.calls += 1
        src = messages[-1].content
        for vi, en in self.table.items():
            src = src.replace(vi, en)
        return _Resp(src)


VI = {
    "Phân tầng theo khoảng cách chất lượng": "Quality-gap stratification",
    "Kiểm định giả thuyết chính xác": "Exact hypothesis testing",
    "Bảng so sánh phương pháp": "Method comparison table",
    "Độ nhạy": "Sensitivity",
    "Phương pháp": "Method",
    "Thiên lệch vị trí": "Position bias",
    "Chúng tôi chia các cặp thành ba tầng dựa trên khoảng cách chất lượng giữa hai câu trả lời của mỗi cặp so sánh": (
        "We split the pairs into three strata based on the quality gap between the two answers of each comparison pair"
    ),
}


def test_headings_tables_json_and_paragraphs_are_translated():
    chart = json.dumps({"type": "bar", "caption": "Độ nhạy", "labels": ["A"], "series": [{"name": "Phương pháp", "values": [1]}]}, ensure_ascii=False)
    text = (
        "# Title\n\n#### 4.4.1 Phân tầng theo khoảng cách chất lượng\n"
        "Chúng tôi chia các cặp thành ba tầng dựa trên khoảng cách chất lượng giữa hai câu trả lời của mỗi cặp so sánh\n\n"
        "| Phương pháp | Độ nhạy |\n|---|---|\n| A | 1 |\n\n"
        f"```chart\n{chart}\n```\n\n## References\n\n[1] Ref."
    )
    out = translate_foreign_paragraphs(text, "en", FakeGateway(VI), None)
    assert "Phân" not in out and "Chúng tôi" not in out and "Phương pháp" not in out and "Độ nhạy" not in out
    assert "#### 4.4.1 Quality-gap stratification" in out
    assert "| Method | Sensitivity |" in out and "|---|---|" in out
    assert json.loads(out.split("```chart\n")[1].split("\n```")[0])["series"][0] == {"name": "Method", "values": [1]}
    assert out.endswith("[1] Ref.")


def test_bad_structure_translation_is_rejected():
    class Bad(FakeGateway):
        def generate(self, messages, model_name=None, **_):
            return _Resp("| only one row |")

    table = "| Phương pháp | Độ nhạy |\n|---|---|\n| A | 1 |"
    assert translate_foreign_paragraphs(table, "en", Bad({}), None) == table


def test_no_gateway_is_noop():
    assert translate_foreign_paragraphs("Độ nhạy của phương pháp", "en", None, None) == "Độ nhạy của phương pháp"
