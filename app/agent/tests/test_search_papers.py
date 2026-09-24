from unittest.mock import patch

from app.agent.tools.retrieve_evidence import retrieve_evidence
from app.core.schemas import Chunk, ScoredChunk


def _scored(id_: str, paper_id: str, score: float) -> ScoredChunk:
    return ScoredChunk(chunk=Chunk(id=id_, paper_id=paper_id, text="t", chunk_index=0), score=score)


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_search_papers_does_not_filter_by_paper_id(mock_hybrid, mock_rerank):
    mock_hybrid.return_value = [_scored("a", "p1", 0.5)]
    mock_rerank.return_value = [_scored("a", "p1", 0.9)]

    from app.agent.tools.search_papers import search_papers

    search_papers("query")

    _, kwargs = mock_hybrid.call_args
    assert kwargs["paper_id"] is None


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_retrieve_evidence_dedups_across_queries_keeping_highest_score(mock_hybrid, mock_rerank):
    mock_hybrid.return_value = []
    mock_rerank.side_effect = [
        [_scored("a", "p1", 0.5)],
        [_scored("a", "p1", 0.9), _scored("b", "p2", 0.3)],
    ]

    evidence = retrieve_evidence(["q1", "q2"])

    by_id = {e.chunk.id: e for e in evidence}
    assert by_id["a"].score == 0.9
    assert "b" in by_id
    assert evidence[0].chunk.id == "a"
