from app.ai.context_builder import build_context
from app.core.schemas import Chunk, ScoredChunk


def _scored(id_: str, text: str, score: float, page: int = 1) -> ScoredChunk:
    return ScoredChunk(chunk=Chunk(id=id_, paper_id="p1", text=text, chunk_index=0, page=page), score=score)


def test_build_context_dedups_by_chunk_id():
    a = _scored("a", "hello world", 1.0)
    a_dup = _scored("a", "hello world", 0.5)

    _, citations = build_context([a, a_dup], token_limit=1000)

    assert len(citations) == 1


def test_build_context_sorts_by_score_desc():
    low = _scored("low", "low score chunk", 0.1)
    high = _scored("high", "high score chunk", 0.9)

    _, citations = build_context([low, high], token_limit=1000)

    assert citations[0].chunk_id == "high"
    assert citations[1].chunk_id == "low"


def test_build_context_always_includes_first_chunk_even_if_over_limit():
    big_text = "word " * 2000
    big = _scored("big", big_text, 1.0)
    small = _scored("small", "short chunk", 0.9)

    _, citations = build_context([big, small], token_limit=10)

    assert len(citations) == 1
    assert citations[0].chunk_id == "big"


def test_build_context_citation_metadata_and_tags():
    c = _scored("x", "some content here", 1.0, page=5)

    text, citations = build_context([c], token_limit=1000)

    assert citations[0].page == 5
    assert citations[0].paper_id == "p1"
    assert "[1]" in text
