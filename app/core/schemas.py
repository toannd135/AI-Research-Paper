"""Pydantic models: Chunk, Citation, ResearchPayload..."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PaperStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ResearchStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Chunk(BaseModel):
    id: str
    paper_id: str
    text: str
    chunk_index: int
    page: int | None = None
    section: str | None = None


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float


class Citation(BaseModel):
    paper_id: str
    chunk_id: str
    page: int | None = None
    section: str | None = None
    text_snippet: str


class ResearchPayload(BaseModel):
    """Context input cho LLM: câu hỏi + các chunk làm bằng chứng."""

    question: str
    chunks: list[ScoredChunk]


class PaperUploadResponse(BaseModel):
    id: str
    filename: str
    status: PaperStatus


class PaperStatusResponse(BaseModel):
    id: str
    filename: str
    status: PaperStatus
    error: str | None = None
    created_at: datetime


class ChatRequest(BaseModel):
    question: str
    paper_id: str | None = None
    conversation_id: str | None = None
    model: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    model: str


class ResearchRequest(BaseModel):
    question: str
    clarification_answers: dict[str, str] | None = None


class ClarificationQuestion(BaseModel):
    text: str
    suggestions: list[str] = Field(default_factory=list)


class ResearchClarificationResponse(BaseModel):
    status: str = "needs_clarification"
    questions: list[ClarificationQuestion]


class ResearchTaskResponse(BaseModel):
    id: str
    status: ResearchStatus
    report: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime


class ExternalSource(BaseModel):
    """1 paper thật lấy từ OpenAlex, dùng để hiển thị ở panel "Research Sources"."""

    id: str
    title: str
    authors: str
    year: int
    publisher: str
    type: str
    doi: str
    relevance: int
    citations: int
    abstract: str | None = None


class ExternalSourceRelation(BaseModel):
    source: str
    target: str
    kind: str


class SourceSearchResponse(BaseModel):
    sources: list[ExternalSource] = Field(default_factory=list)
    relations: list[ExternalSourceRelation] = Field(default_factory=list)
