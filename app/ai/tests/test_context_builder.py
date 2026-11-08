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


def _paper_chunk(pid: str, idx: int, score: float, words: int = 800) -> ScoredChunk:
    text = " ".join(f"{pid}w{i}" for i in range(words))
    return ScoredChunk(chunk=Chunk(id=f"{pid}-{idx}", paper_id=pid, text=text, chunk_index=idx, page=1), score=score)


def test_diversify_trims_first_chunks_so_every_paper_fits():
    # 55 paper x ~2900 token/chunk vượt xa limit: vẫn phải có đủ 55 paper trong context
    chunks = [_paper_chunk(f"p{i}", 0, 1.0 - i / 100) for i in range(55)]
    chunks += [_paper_chunk(f"p{i}", 1, 0.5 - i / 1000) for i in range(55)]

    text, citations = build_context(chunks, token_limit=22000, diversify=True)

    assert {c.paper_id for c in citations} == {f"p{i}" for i in range(55)}
    assert len(text) / 3 <= 22000 * 1.1
    assert "p0w0" in text  # cắt từ đầu chunk, giữ nguyên văn để đối chiếu với PDF


def test_diversify_keeps_full_chunks_when_they_fit():
    chunks = [_paper_chunk(f"p{i}", 0, 1.0 - i / 10, words=50) for i in range(3)]

    text, citations = build_context(chunks, token_limit=22000, diversify=True)

    assert len(citations) == 3
    assert all(c.chunk.text in text for c in chunks)
