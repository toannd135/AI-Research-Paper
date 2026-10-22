from unittest.mock import MagicMock, patch

from app.ai.external.openalex_client import search_works


@patch("app.ai.external.openalex_client.httpx.get")
def test_search_works_strips_markdown_wildcards(mock_get):
    mock_get.return_value = MagicMock(json=lambda: {"results": [{"id": "W1"}], "meta": {}})

    search_works("research paper on **Few-Shot Learning (FSL)**", count=5)

    assert mock_get.call_args.kwargs["params"]["search"] == "research paper on  Few-Shot Learning (FSL)"
