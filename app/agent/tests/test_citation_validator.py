from app.agent.evidence.citation_validator import find_invalid_citations
from app.core.schemas import Citation


def _citation(paper_id: str) -> Citation:
    return Citation(paper_id=paper_id, chunk_id="c1", text_snippet="...")


def test_no_invalid_citations_when_all_markers_in_range():
    citations = [_citation("p1"), _citation("p2")]
    draft = "Câu đầu [1]. Câu sau [2]."

    assert find_invalid_citations(draft, citations) == []


def test_flags_marker_out_of_range():
    citations = [_citation("p1")]
    draft = "Câu này [1] và câu này [2] không có nguồn."

    assert find_invalid_citations(draft, citations) == [2]


def test_no_markers_is_valid():
    assert find_invalid_citations("Không có trích dẫn nào.", []) == []
