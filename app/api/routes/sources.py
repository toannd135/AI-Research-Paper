"""Tìm nguồn học thuật qua OpenAlex cho màn hình research của frontend."""

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.core.schemas import ExternalSource, SourceRelation, SourceSearchResponse

router = APIRouter(prefix="/sources", tags=["sources"])

_SELECT_FIELDS = ",".join(
    [
        "id",
        "display_name",
        "authorships",
        "publication_year",
        "primary_location",
        "type",
        "doi",
        "relevance_score",
        "cited_by_count",
        "abstract_inverted_index",
        "referenced_works",
        "related_works",
    ]
)

_TYPE_LABELS = {
    "article": "Journal Article",
    "preprint": "Preprint",
    "review": "Review",
    "book-chapter": "Book Chapter",
    "book": "Book",
    "dissertation": "Thesis",
    "dataset": "Dataset",
}


def _short_id(openalex_id: str) -> str:
    return openalex_id.rsplit("/", 1)[-1]


def _format_authors(authorships: list[dict]) -> str:
    names = [a["author"]["display_name"] for a in authorships if a.get("author", {}).get("display_name")]
    if not names:
        return "Unknown"
    if len(names) > 3:
        return ", ".join(names[:3]) + " et al."
    return ", ".join(names)


def _publisher(work: dict) -> str:
    source = (work.get("primary_location") or {}).get("source") or {}
    return source.get("display_name") or source.get("host_organization_name") or "Unknown"


def _abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None
    positions = [(pos, word) for word, poses in inverted_index.items() for pos in poses]
    return " ".join(word for _, word in sorted(positions))


def _relevance(score: float | None, max_score: float) -> int:
    # Chuẩn hoá relevance_score của OpenAlex về thang 50-99 (kết quả tốt nhất ≈ 99)
    if not score or max_score <= 0:
        return 50
    return round(50 + 49 * score / max_score)


def build_response(works: list[dict]) -> SourceSearchResponse:
    works = [w for w in works if w.get("display_name") and w.get("publication_year")]
    max_score = max((w.get("relevance_score") or 0 for w in works), default=0)
    ids = {_short_id(w["id"]) for w in works}

    sources: list[ExternalSource] = []
    relations: list[SourceRelation] = []
    seen_edges: set[tuple[str, str]] = set()

    for w in works:
        wid = _short_id(w["id"])
        sources.append(
            ExternalSource(
                id=wid,
                title=w["display_name"],
                authors=_format_authors(w.get("authorships") or []),
                year=w["publication_year"],
                publisher=_publisher(w),
                type=_TYPE_LABELS.get(w.get("type") or "", (w.get("type") or "Other").title()),
                doi=(w.get("doi") or "").removeprefix("https://doi.org/"),
                relevance=_relevance(w.get("relevance_score"), max_score),
                citations=w.get("cited_by_count") or 0,
                abstract=_abstract(w.get("abstract_inverted_index")),
            )
        )
        # Chỉ giữ cạnh giữa các nguồn nằm trong tập kết quả
        for kind, field in (("cites", "referenced_works"), ("related", "related_works")):
            for ref in w.get(field) or []:
                target = _short_id(ref)
                edge = tuple(sorted((wid, target)))
                if target in ids and target != wid and edge not in seen_edges:
                    seen_edges.add(edge)
                    relations.append(SourceRelation(source=wid, target=target, kind=kind))

    return SourceSearchResponse(sources=sources, relations=relations)


@router.get("/search", response_model=SourceSearchResponse)
async def search_sources(
    query: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
) -> SourceSearchResponse:
    settings = get_settings()
    params = {"search": query, "per_page": limit, "select": _SELECT_FIELDS}
    if settings.openalex_mailto:
        params["mailto"] = settings.openalex_mailto

    try:
        async with httpx.AsyncClient(timeout=settings.openalex_timeout) as client:
            resp = await client.get(f"{settings.openalex_base_url}/works", params=params)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAlex trả lỗi {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=504, detail="Không kết nối được tới OpenAlex") from exc

    return build_response(resp.json().get("results", []))
