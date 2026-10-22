from unittest.mock import patch

from app.ai.external import query_rewrite
from app.ai.external.query_rewrite import to_english_search_query


def test_short_english_query_skips_llm():
    with patch.object(query_rewrite, "_rewrite") as rewrite:
        assert to_english_search_query("few-shot learning") == "few-shot learning"
    rewrite.assert_not_called()


def test_vietnamese_query_is_rewritten_to_english():
    with patch.object(query_rewrite, "_rewrite", return_value="hybrid retrieval-augmented generation") as rewrite:
        out = to_english_search_query("Viết cho tôi bài báo về mô hình hybird rag")
    assert out == "hybrid retrieval-augmented generation"
    rewrite.assert_called_once()


def test_llm_failure_falls_back_to_cleaned_original():
    with patch.object(query_rewrite, "_rewrite", side_effect=RuntimeError("429")):
        assert to_english_search_query('**Mô hình** "rag" tiếng Việt') == "Mô hình rag tiếng Việt"
