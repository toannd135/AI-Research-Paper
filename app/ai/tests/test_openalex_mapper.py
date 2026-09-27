from app.ai.external.openalex_mapper import build_source_search_response

WORK_A = {
    "id": "https://openalex.org/W111",
    "title": "Retrieval-Augmented Generation Survey",
    "authorships": [
        {"author": {"display_name": "Patrick Lewis"}},
        {"author": {"display_name": "Ethan Perez"}},
    ],
    "publication_year": 2024,
    "primary_location": {"source": {"display_name": "arXiv"}},
    "type": "preprint",
    "doi": "https://doi.org/10.48550/arXiv.2312.10997",
    "cited_by_count": 812,
    "referenced_works": ["https://openalex.org/W222"],
    "concepts": [{"id": "C1"}, {"id": "C2"}, {"id": "C3"}],
    "abstract_inverted_index": {"Hello": [0], "world": [1]},
}

WORK_B = {
    "id": "https://openalex.org/W222",
    "title": "Hybrid Retrieval Strategies",
    "authorships": [{"author": {"display_name": "Alvarez, D."}}],
    "publication_year": 2023,
    "primary_location": {"source": {"display_name": "ACL Anthology"}},
    "type": "conference-paper",
    "doi": "https://doi.org/10.18653/v1/2023.acl-long.221",
    "cited_by_count": 210,
    "referenced_works": [],
    "concepts": [{"id": "C1"}, {"id": "C2"}],
    "abstract_inverted_index": None,
}

WORK_C_NO_LINK = {
    "id": "https://openalex.org/W333",
    "title": "Unrelated Topic",
    "authorships": [],
    "publication_year": 2022,
    "primary_location": {},
    "type": None,
    "doi": None,
    "cited_by_count": 0,
    "referenced_works": [],
    "concepts": [],
    "abstract_inverted_index": None,
}


def test_maps_basic_fields():
    result = build_source_search_response([WORK_A, WORK_B])

    a = result.sources[0]
    assert a.id == "W111"
    assert a.title == "Retrieval-Augmented Generation Survey"
    assert a.authors == "Patrick Lewis, Ethan Perez"
    assert a.year == 2024
    assert a.publisher == "arXiv"
    assert a.type == "Preprint"
    assert a.doi == "10.48550/arXiv.2312.10997"
    assert a.citations == 812
    assert a.abstract == "Hello world"


def test_missing_fields_fallback_gracefully():
    result = build_source_search_response([WORK_C_NO_LINK])
    c = result.sources[0]
    assert c.authors == "Không rõ tác giả"
    assert c.publisher == "Không rõ nguồn"
    assert c.type == "Khác"
    assert c.doi == ""
    assert c.abstract is None


def test_relevance_decreases_by_rank():
    result = build_source_search_response([WORK_A, WORK_B, WORK_C_NO_LINK])
    scores = [s.relevance for s in result.sources]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[-1]


def test_cites_relation_from_referenced_works():
    result = build_source_search_response([WORK_A, WORK_B])
    cites = [r for r in result.relations if r.kind == "cites"]
    assert len(cites) == 1
    assert cites[0].source == "W111"
    assert cites[0].target == "W222"


def test_related_relation_from_shared_concepts_without_direct_citation():
    result = build_source_search_response([WORK_B, WORK_A])
    # WORK_A cites WORK_B -> đã có quan hệ 'cites', không nên có thêm 'related' trùng cặp đó.
    pairs = {frozenset((r.source, r.target)) for r in result.relations}
    assert len(pairs) == 1


def test_no_relation_for_unrelated_work():
    result = build_source_search_response([WORK_A, WORK_B, WORK_C_NO_LINK])
    touches_c = [r for r in result.relations if "W333" in (r.source, r.target)]
    assert touches_c == []
