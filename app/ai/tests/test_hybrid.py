from unittest.mock import patch

import pytest

from app.ai.retrieval.hybrid import _normalize, search_hybrid
from app.core.config import get_settings
from app.core.schemas import Chunk, ScoredChunk


def _chunk(id_: str) -> Chunk:
    return Chunk(id=id_, paper_id="p1", text=f"text-{id_}", chunk_index=0)


def test_normalize_min_max():
    scored = [ScoredChunk(chunk=_chunk("a"), score=1.0), ScoredChunk(chunk=_chunk("b"), score=3.0)]
    norm = _normalize(scored)
    assert norm["a"] == 0.0
    assert norm["b"] == 1.0


def test_normalize_empty_list_returns_empty_dict():
    assert _normalize([]) == {}


def test_normalize_equal_scores_returns_one():
    scored = [ScoredChunk(chunk=_chunk("a"), score=2.0), ScoredChunk(chunk=_chunk("b"), score=2.0)]
    assert _normalize(scored) == {"a": 1.0, "b": 1.0}


@patch("app.ai.retrieval.hybrid.search_bm25")
@patch("app.ai.retrieval.hybrid.search_vector")
def test_search_hybrid_combines_by_alpha_beta(mock_vector, mock_bm25):
    mock_vector.return_value = [
        ScoredChunk(chunk=_chunk("a"), score=1.0),
        ScoredChunk(chunk=_chunk("b"), score=0.0),
    ]
    mock_bm25.return_value = [
        ScoredChunk(chunk=_chunk("a"), score=0.0),
        ScoredChunk(chunk=_chunk("b"), score=1.0),
    ]

    settings = get_settings()
    results = search_hybrid("query", top_k=2)
    scores = {r.chunk.id: r.score for r in results}

    assert scores["a"] == pytest.approx(settings.hybrid_alpha * 1.0 + settings.hybrid_beta * 0.0)
    assert scores["b"] == pytest.approx(settings.hybrid_alpha * 0.0 + settings.hybrid_beta * 1.0)


@patch("app.ai.retrieval.hybrid.search_bm25")
@patch("app.ai.retrieval.hybrid.search_vector")
def test_search_hybrid_respects_top_k(mock_vector, mock_bm25):
    mock_vector.return_value = [ScoredChunk(chunk=_chunk(f"v{i}"), score=float(i)) for i in range(5)]
    mock_bm25.return_value = []

    results = search_hybrid("query", top_k=2)

    assert len(results) == 2
