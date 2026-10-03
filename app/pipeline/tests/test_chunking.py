from app.pipeline.chunking.semantic_chunker import chunk_pages as semantic_chunk_pages
from app.pipeline.chunking.simple_chunker import chunk_pages as simple_chunk_pages
from app.pipeline.parser.pdf_parser import PageText


def test_simple_chunker_empty_pages_returns_empty():
    assert simple_chunk_pages("paper-1", []) == []


def test_simple_chunker_splits_long_text():
    text = "0123456789" * 100  # 1000 ký tự
    pages = [PageText(page=1, text=text)]

    chunks = simple_chunk_pages("paper-1", pages, chunk_size=400, overlap=100)

    assert len(chunks) >= 2
    assert all(c.paper_id == "paper-1" for c in chunks)
    assert all(c.page == 1 for c in chunks)


def test_simple_chunker_overlap_between_consecutive_chunks():
    text = "0123456789" * 100
    pages = [PageText(page=1, text=text)]

    chunks = simple_chunk_pages("paper-1", pages, chunk_size=400, overlap=100)

    end_of_first = chunks[0].text[-100:]
    start_of_second = chunks[1].text[:100]
    assert end_of_first == start_of_second


def test_semantic_chunker_empty_pages_returns_empty():
    assert semantic_chunk_pages("paper-1", []) == []


def test_semantic_chunker_tags_section_from_heading():
    text = "1. Introduction\n\nSome intro text.\n\n2. Method\n\nSome method text."
    pages = [PageText(page=1, text=text)]

    chunks = semantic_chunk_pages("paper-1", pages, chunk_size=1000)

    assert len(chunks) >= 1
    assert chunks[0].section == "1. Introduction"
