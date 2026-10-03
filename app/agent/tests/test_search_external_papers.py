"""Unit test cho tool search_external_papers kết nối OpenAlex."""

from unittest.mock import patch

from app.agent.tools.search_external_papers import search_external_papers
from app.ai.external.openalex_client import OpenAlexError


@patch("app.agent.tools.search_external_papers.search_works")
def test_search_external_papers_success(mock_search_works):
    mock_search_works.return_value = [
        {
            "id": "https://openalex.org/W12345",
            "title": "Attention Is All You Need",
            "authorships": [{"author": {"display_name": "Vaswani et al."}}],
            "publication_year": 2017,
            "cited_by_count": 90000,
            "abstract_inverted_index": {"The": [0], "transformer": [1]},
        }
    ]

    response = search_external_papers("Transformer", count=1)
    assert len(response.sources) == 1
    assert response.sources[0].id == "W12345"
    assert response.sources[0].title == "Attention Is All You Need"
    assert response.sources[0].year == 2017
    assert response.sources[0].citations == 90000


@patch("app.agent.tools.search_external_papers.search_works")
def test_search_external_papers_handles_error(mock_search_works):
    mock_search_works.side_effect = OpenAlexError("API down")
    response = search_external_papers("Transformer", count=1)
    assert response.sources == []
    assert response.relations == []


def test_search_external_papers_empty_query():
    response = search_external_papers("   ")
    assert response.sources == []
    assert response.relations == []
