from app.api.routes.sources import build_response


def _work(wid, score, refs=(), related=()):
    return {
        "id": f"https://openalex.org/{wid}",
        "display_name": f"Paper {wid}",
        "authorships": [{"author": {"display_name": n}} for n in ["A", "B", "C", "D"]],
        "publication_year": 2023,
        "primary_location": {"source": {"display_name": "arXiv"}},
        "type": "preprint",
        "doi": "https://doi.org/10.1/x",
        "relevance_score": score,
        "cited_by_count": 5,
        "abstract_inverted_index": {"world": [1], "hello": [0]},
        "referenced_works": [f"https://openalex.org/{r}" for r in refs],
        "related_works": [f"https://openalex.org/{r}" for r in related],
    }


def test_build_response_maps_fields_and_relations():
    res = build_response([_work("W1", 100, refs=["W2", "W9"]), _work("W2", 50, related=["W1"])])
    s1, s2 = res.sources
    assert s1.id == "W1" and s1.relevance == 99 and s2.relevance == 74
    assert s1.authors == "A, B, C et al."
    assert s1.abstract == "hello world" and s1.doi == "10.1/x" and s1.type == "Preprint"
    # W9 ngoài tập kết quả bị bỏ; cạnh W2->W1 trùng với W1->W2 nên chỉ giữ một
    assert [(r.source, r.target, r.kind) for r in res.relations] == [("W1", "W2", "cites")]
