"""Pydantic models và Interface contract giữa các Dev: Chunk, Citation, ResearchPayload, API Schemas..."""

from __future__ import annotations

import operator
from datetime import datetime
from enum import Enum
from typing import Annotated, TypedDict

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Core Domain Models
# ---------------------------------------------------------------------------


class PaperRef(BaseModel):
    """Thông tin tham chiếu bài báo khoa học."""

    model_config = ConfigDict(extra="ignore")

    paper_id: str = Field(..., description="ID định danh duy nhất của bài báo")
    title: str = Field(..., description="Tiêu đề bài báo")
    authors: list[str] = Field(default_factory=list, description="Danh sách tác giả")
    year: int | None = Field(default=None, description="Năm xuất bản")


class Chunk(BaseModel):
    """Đoạn văn bản trích xuất từ bài báo, tương thích 2 chiều giữa Dev 1, 2 và 3."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = Field(default="", description="ID định danh chunk")
    paper_id: str = Field(..., description="ID bài báo sở hữu chunk")
    text: str = Field(default="", description="Nội dung văn bản của chunk")
    chunk_index: int = Field(default=0, description="Chỉ số thứ tự chunk")
    page: int | None = Field(default=None, description="Số trang PDF gốc")
    section: str | None = Field(default=None, description="Tên mục/phần")
    score: float | None = Field(default=None, description="Điểm relevance/similarity")

    def __init__(self, **data):
        # Hỗ trợ alias backward-compatibility cho chunk_id, content, page_number, section_title
        if "chunk_id" in data and "id" not in data:
            data["id"] = data["chunk_id"]
        if "content" in data and "text" not in data:
            data["text"] = data["content"]
        if "page_number" in data and "page" not in data:
            data["page"] = data["page_number"]
        if "section_title" in data and "section" not in data:
            data["section"] = data["section_title"]
        super().__init__(**data)

    @property
    def chunk_id(self) -> str:
        return self.id

    @property
    def content(self) -> str:
        return self.text

    @property
    def page_number(self) -> int | None:
        return self.page

    @property
    def section_title(self) -> str | None:
        return self.section


class ScoredChunk(BaseModel):
    """Chunk đi kèm điểm liên quan sau khi search/rerank."""

    chunk: Chunk
    score: float

    @property
    def id(self) -> str:
        return self.chunk.id

    @property
    def chunk_id(self) -> str:
        return self.chunk.id

    @property
    def paper_id(self) -> str:
        return self.chunk.paper_id

    @property
    def text(self) -> str:
        return self.chunk.text

    @property
    def content(self) -> str:
        return self.chunk.text

    @property
    def page(self) -> int | None:
        return self.chunk.page

    @property
    def page_number(self) -> int | None:
        return self.chunk.page

    @property
    def section(self) -> str | None:
        return self.chunk.section

    @property
    def section_title(self) -> str | None:
        return self.chunk.section

    def get(self, key: str, default=None):
        if hasattr(self, key):
            return getattr(self, key)
        return default



class Citation(BaseModel):
    """Trích dẫn bằng chứng cụ thể gắn liền với câu trả lời / báo cáo."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    paper_id: str = Field(..., description="ID bài báo được trích dẫn")
    chunk_id: str = Field(..., description="ID chunk được trích dẫn")
    page: int | None = Field(default=None, description="Số trang tương ứng của chunk")
    section: str | None = Field(default=None, description="Mục được trích dẫn")
    text_snippet: str = Field(default="", description="Đoạn trích dẫn nguyên văn")

    def __init__(self, **data):
        # Hỗ trợ alias page_number, quoted_text
        if "page_number" in data and "page" not in data:
            data["page"] = data["page_number"]
        if "quoted_text" in data and "text_snippet" not in data:
            data["text_snippet"] = data["quoted_text"]
        super().__init__(**data)

    @property
    def page_number(self) -> int | None:
        return self.page

    @property
    def quoted_text(self) -> str:
        return self.text_snippet


class ResearchPayload(BaseModel):
    """Context input cho LLM: câu hỏi + các chunk làm bằng chứng."""

    question: str
    chunks: list[ScoredChunk]


# ---------------------------------------------------------------------------
# Tool Input Schemas (LangChain @tool args_schema)
# ---------------------------------------------------------------------------


class SearchPapersInput(BaseModel):
    """Input schema cho tool search_papers."""

    query: str = Field(..., description="Từ khóa hoặc câu hỏi tìm kiếm bài báo")
    top_k: int = Field(default=5, ge=1, le=20, description="Số lượng bài báo tối đa")


class RetrieveEvidenceInput(BaseModel):
    """Input schema cho tool retrieve_evidence."""

    query: str = Field(..., description="Nội dung cần tìm bằng chứng")
    paper_id: str | None = Field(
        default=None, description="ID bài báo cụ thể cần trích xuất (nếu có)"
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Số chunk tối đa trả về")


# ---------------------------------------------------------------------------
# Agent State Contract
# ---------------------------------------------------------------------------


class ResearchState(TypedDict, total=False):
    """State quản lý luồng nghiên cứu trong LangGraph."""

    question: str
    search_queries: list[str]
    papers: list[PaperRef]
    evidence: list[ScoredChunk]
    draft: str
    answer: str
    citations: list[Citation]
    critique_feedback: str | None
    iterations: int
    report: str
    steps: Annotated[list[str], operator.add]


# ---------------------------------------------------------------------------
# API / Celery Request & Response Schemas
# ---------------------------------------------------------------------------


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
    question: str = Field(..., min_length=3, description="Câu hỏi nghiên cứu")
    clarification_answers: dict[str, str] | None = None
    paper_ids: list[str] | None = Field(
        default=None, description="Danh sách paper_ids giới hạn tìm kiếm"
    )


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


class ResearchResponse(BaseModel):
    """Response trả về kết quả nghiên cứu hoàn chỉnh."""

    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)


class ExternalSource(BaseModel):
    """1 paper thật lấy từ OpenAlex, dùng để hiển thị ở panel 'Research Sources'."""

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
