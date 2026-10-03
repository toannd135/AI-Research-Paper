"""Map Work JSON thô từ OpenAlex sang ExternalSource/ExternalSourceRelation (schema chung)."""

import re

from app.core.schemas import (
    ExternalSource,
    ExternalSourceRelation,
    SourceSearchResponse,
)

_ID_TAIL_RE = re.compile(r"/([A-Za-z0-9]+)$")


def _short_id(openalex_url: str | None) -> str | None:
    if not openalex_url:
        return None
    match = _ID_TAIL_RE.search(openalex_url)
    return match.group(1) if match else openalex_url


def _authors(work: dict) -> str:
    names = [
        a["author"]["display_name"]
        for a in work.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]
    if not names:
        return "Không rõ tác giả"
    if len(names) > 3:
        return ", ".join(names[:3]) + " et al."
    return ", ".join(names)


def _publisher(work: dict) -> str:
    source = (work.get("primary_location") or {}).get("source") or {}
    return source.get("display_name") or "Không rõ nguồn"


def _type_label(work: dict) -> str:
    raw = work.get("type") or ""
    if not raw:
        return "Khác"
    return raw.replace("-", " ").title()


def _doi(work: dict) -> str:
    return (work.get("doi") or "").removeprefix("https://doi.org/")


def _abstract(work: dict) -> str | None:
    inverted = work.get("abstract_inverted_index")
    if not inverted:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


def _relevance_by_rank(rank: int, total: int) -> int:
    """OpenAlex trả kết quả `search` đã sắp theo relevance giảm dần; quy đổi thứ hạng
    sang thang 60-97 để đồng nhất với UI (relevance %) thay vì dùng relevance_score thô
    (không có biên trên cố định, khó hiển thị thành %)."""
    if total <= 1:
        return 90
    return 97 - round((rank / (total - 1)) * 37)


def build_source_search_response(works: list[dict]) -> SourceSearchResponse:
    total = len(works)
    ids: list[str] = [_short_id(work.get("id")) or f"src_{rank}" for rank, work in enumerate(works)]

    sources = [
        ExternalSource(
            id=ids[rank],
            title=work.get("title") or work.get("display_name") or "Không có tiêu đề",
            authors=_authors(work),
            year=work.get("publication_year") or 0,
            publisher=_publisher(work),
            type=_type_label(work),
            doi=_doi(work),
            relevance=_relevance_by_rank(rank, total),
            citations=work.get("cited_by_count") or 0,
            abstract=_abstract(work),
        )
        for rank, work in enumerate(works)
    ]

    relations: list[ExternalSourceRelation] = []
    seen_pairs: set[frozenset[str]] = set()

    for i, work in enumerate(works):
        referenced = {_short_id(r) for r in work.get("referenced_works", [])}
        for j, other_id in enumerate(ids):
            if i == j or other_id not in referenced:
                continue
            pair = frozenset((ids[i], other_id))
            if pair in seen_pairs:
                continue
            relations.append(ExternalSourceRelation(source=ids[i], target=other_id, kind="cites"))
            seen_pairs.add(pair)

    concept_ids = [{c.get("id") for c in work.get("concepts", [])[:5]} for work in works]
    for i in range(total):
        if not concept_ids[i]:
            continue
        for j in range(i + 1, total):
            pair = frozenset((ids[i], ids[j]))
            if pair in seen_pairs or not concept_ids[j]:
                continue
            if len(concept_ids[i] & concept_ids[j]) >= 2:
                relations.append(ExternalSourceRelation(source=ids[i], target=ids[j], kind="related"))
                seen_pairs.add(pair)

    return SourceSearchResponse(sources=sources, relations=relations)
