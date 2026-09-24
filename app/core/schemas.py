"""Interface contract giữa các Dev: Pydantic schemas và State definitions."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel, ConfigDict, Field

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
    """Đoạn văn bản trích xuất từ bài báo, dùng cho retrieval và citation."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: str = Field(..., description="ID định danh duy nhất của chunk")
    paper_id: str = Field(..., description="ID bài báo sở hữu chunk")
    content: str = Field(..., description="Nội dung văn bản của chunk")
    page_number: int | None = Field(default=None, description="Số trang PDF gốc")
    section_title: str | None = Field(
        default=None, description="Tên mục/phần (ví dụ: Abstract, Methods)"
    )
    score: float | None = Field(default=None, description="Điểm relevance/similarity")


class Citation(BaseModel):
    """Trích dẫn bằng chứng cụ thể gắn liền với câu trả lời."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: str = Field(..., description="ID chunk được trích dẫn")
    paper_id: str = Field(..., description="ID bài báo được trích dẫn")
    page_number: int | None = Field(
        default=None, description="Số trang tương ứng của chunk"
    )
    quoted_text: str = Field(
        ..., description="Đoạn trích dẫn nguyên văn dùng làm bằng chứng"
    )


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


class ResearchState(TypedDict):
    """State quản lý luồng nghiên cứu trong LangGraph."""

    question: str
    papers: list[PaperRef]
    evidence: list[Chunk]
    answer: str
    citations: list[Citation]
    steps: Annotated[list[str], operator.add]


# ---------------------------------------------------------------------------
# API / Celery Request & Response Schemas
# ---------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    """Payload gửi vào API nghiên cứu / Celery task."""

    question: str = Field(..., min_length=3, description="Câu hỏi nghiên cứu")
    paper_ids: list[str] | None = Field(
        default=None, description="Danh sách paper_ids giới hạn tìm kiếm"
    )


class ResearchResponse(BaseModel):
    """Response trả về kết quả nghiên cứu hoàn chỉnh."""

    question: str
    answer: str
    citations: list[Citation]
    steps: list[str]
