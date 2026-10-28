"""State chung cho LangGraph research pipeline."""

from typing import TypedDict

from app.core.schemas import Citation, ScoredChunk


class ResearchState(TypedDict, total=False):
    question: str
    search_queries: list[str]
    evidence: list[ScoredChunk]
    draft: str
    citations: list[Citation]
    critique_feedback: str | None
    iterations: int
    research_mode: str
    language: str  # mã ISO 639-1 của ngôn ngữ bài báo đầu ra (mặc định theo câu hỏi người dùng)
    baseline_analysis: str | None
    field: str  # khóa FIELD_PROFILES (app/agent/profiles.py); plan_node tự đoán nếu thiếu
    audience: str  # lecturer | student | professional
    figures: list[dict]  # hình thật trích từ PDF đã upload, id F1..Fn (synthesize_node)
    report: str
    contribution_type: str  # khóa CONTRIBUTION_TYPES (app/agent/research_model.py); plan_node tự đoán nếu thiếu
    methodology: str
    paper_type: str
    topic: str
    target_venue: str | None
    user_results: str | None  # kết quả thực nghiệm người dùng tự cung cấp (tùy chọn)
    research_model: dict  # Research Knowledge Model đã kiểm chứng (nodes/model_node.py)
