"""GET /sources/search — tìm nguồn học thuật thật từ OpenAlex theo chủ đề nghiên cứu."""

from fastapi import APIRouter, HTTPException, Query

from app.ai.external.openalex_client import OpenAlexError, search_works
from app.ai.external.openalex_mapper import build_source_search_response
from app.core.schemas import SourceSearchResponse

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/search", response_model=SourceSearchResponse)
def search_sources(
    query: str = Query(..., min_length=1),
    limit: int = Query(150, ge=1, le=300),
) -> SourceSearchResponse:
    try:
        works = search_works(query, count=limit)
    except OpenAlexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return build_source_search_response(works)
