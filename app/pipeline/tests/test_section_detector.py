from app.pipeline.parser.pdf_parser import PageText
from app.pipeline.parser.section_detector import assign_section, detect_sections, is_heading


def test_is_heading_detects_numbered_heading():
    assert is_heading("1. Introduction")
    assert is_heading("2.1 Related Work")


def test_is_heading_detects_common_section_name():
    assert is_heading("Abstract")
    assert is_heading("References")


def test_is_heading_rejects_normal_sentence():
    assert not is_heading("This paper proposes a new method for retrieval.")
    assert not is_heading("")


def test_detect_sections_finds_all_headings():
    text = "1. Introduction\n\nSome intro text.\n\n2. Method\n\nSome method text."
    pages = [PageText(page=1, text=text)]

    sections = detect_sections(pages)
    titles = [s.title for s in sections]

    assert "1. Introduction" in titles
    assert "2. Method" in titles


def test_assign_section_returns_closest_preceding_heading():
    text = "1. Introduction\n\nSome intro text.\n\n2. Method\n\nSome method text."
    pages = [PageText(page=1, text=text)]
    sections = detect_sections(pages)

    method_offset = text.index("2. Method")
    assert assign_section(1, method_offset, sections) == "2. Method"
    assert assign_section(1, 0, sections) == "1. Introduction"
