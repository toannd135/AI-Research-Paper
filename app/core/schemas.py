"""Pydantic models: Chunk, Citation, ResearchPayload..."""

from typing import Literal

from pydantic import BaseModel


class ExternalSource(BaseModel):
    """Nguồn học thuật tìm từ OpenAlex — khớp `ApiExternalSource` ở frontend."""

    id: str
    title: str
    authors: str
    year: int
    publisher: str
    type: str
    doi: str
    relevance: int  # 0-100
    citations: int
    abstract: str | None = None


class SourceRelation(BaseModel):
    source: str
    target: str
    kind: Literal["cites", "related"]


class SourceSearchResponse(BaseModel):
    sources: list[ExternalSource]
    relations: list[SourceRelation]
