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


def test_detects_citation_misattribution():
    from app.agent.evidence.citation_validator import find_citation_misattributions

    citations = [
        Citation(paper_id="HippoRAG: Neurobiologically Inspired Long-Term Memory", chunk_id="c1", text_snippet="hipporag details"),
        Citation(paper_id="Pan et al. Survey on Self-Correction Strategies", chunk_id="c2", text_snippet="self-correction overview"),
    ]

    # IRCoT cited with [1] which is HippoRAG -> MISMATCH!
    draft = "Mô hình IRCoT [1] thực hiện multi-hop reasoning. Khảo sát của Pan et al. [2] tổng hợp self-correction."
    mismatches = find_citation_misattributions(draft, citations)

    assert len(mismatches) == 1
    assert "IRCoT [1]" in mismatches[0]
    assert "HippoRAG" in mismatches[0]


def test_ignores_common_stopwords_in_citations():
    from app.agent.evidence.citation_validator import find_citation_misattributions

    citations = [Citation(paper_id="Paper 1", chunk_id="c1", text_snippet="text")]
    draft = "As shown in Table [1] and Section [1], the result is valid."

    assert find_citation_misattributions(draft, citations) == []
