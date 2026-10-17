"""POST /research, GET /research, GET /research/{id}, DELETE /research/{id}, GET /research/{id}/pdf."""

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.clarify import clarify
from app.agent.format_sanitizer import sanitize_academic_markdown
from app.ai.llm_gateway.base import LLMGatewayError
from app.api.models.research_task import ResearchTask
from app.core.database import get_db
from app.core.schemas import (
    Citation,
    ResearchClarificationResponse,
    ResearchListResponse,
    ResearchRequest,
    ResearchStatus,
    ResearchTaskResponse,
    ResearchTaskSummary,
)
from app.pipeline.tasks import run_research

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/research", tags=["research"])


def _load_citations(task: ResearchTask) -> list[Citation]:
    if not task.citations:
        return []
    try:
        return [Citation(**c) for c in json.loads(task.citations)]
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("Citations của task %s không parse được, trả về rỗng", task.id)
        return []


def _to_response(task: ResearchTask) -> ResearchTaskResponse:
    return ResearchTaskResponse(
        id=task.id,
        question=task.question,
        refined_question=task.refined_question,
        status=ResearchStatus(task.status),
        report=task.report,
        citations=_load_citations(task),
        error=task.error,
        created_at=task.created_at,
    )


def _to_summary(task: ResearchTask) -> ResearchTaskSummary:
    return ResearchTaskSummary(
        id=task.id,
        question=task.question,
        refined_question=task.refined_question,
        status=ResearchStatus(task.status),
        has_report=bool(task.report),
        citation_count=len(_load_citations(task)),
        error=task.error,
        created_at=task.created_at,
    )


@router.post("/", response_model=ResearchTaskResponse | ResearchClarificationResponse)
def create_research(payload: ResearchRequest, db: Session = Depends(get_db)):
    try:
        result = clarify(payload.question, payload.clarification_answers)
    except LLMGatewayError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if result["status"] == "needs_clarification":
        return ResearchClarificationResponse(questions=result["questions"])

    task = ResearchTask(
        question=payload.question,
        clarification_answers=json.dumps(payload.clarification_answers, ensure_ascii=False)
        if payload.clarification_answers
        else None,
        refined_question=result["refined_question"],
        status=ResearchStatus.PENDING.value,
    )
    db.add(task)
    db.commit()

    run_research.delay(task.id)
    logger.info("Tạo research task %s: %s", task.id, payload.question[:80])

    return _to_response(task)


@router.get("", response_model=ResearchListResponse)
def list_research(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: ResearchStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> ResearchListResponse:
    stmt = select(ResearchTask)
    count_stmt = select(func.count()).select_from(ResearchTask)
    if status_filter is not None:
        stmt = stmt.where(ResearchTask.status == status_filter.value)
        count_stmt = count_stmt.where(ResearchTask.status == status_filter.value)

    total = db.scalar(count_stmt) or 0
    tasks = db.scalars(stmt.order_by(ResearchTask.created_at.desc()).limit(limit).offset(offset)).all()
    return ResearchListResponse(items=[_to_summary(t) for t in tasks], total=total, limit=limit, offset=offset)


@router.get("/{task_id}", response_model=ResearchTaskResponse)
def get_research(task_id: str, db: Session = Depends(get_db)) -> ResearchTaskResponse:
    task = db.get(ResearchTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Research task không tồn tại")
    return _to_response(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_research(task_id: str, db: Session = Depends(get_db)) -> None:
    task = db.get(ResearchTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Research task không tồn tại")
    # Cho phép xoá cả task đang chạy/kẹt (worker chết); worker tự bỏ qua khi thấy task đã bị xoá.
    db.delete(task)
    db.commit()


@router.get("/{task_id}/pdf")
def export_research_pdf(
    task_id: str,
    engine: Literal["typst", "html"] = "typst",
    download: bool = False,
    db: Session = Depends(get_db),
) -> Response:
    task = db.get(ResearchTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Research task không tồn tại")
    if not task.report:
        raise HTTPException(status_code=409, detail="Research task chưa có báo cáo")

    clean_report = sanitize_academic_markdown(task.report)
    citations_data = json.loads(task.citations) if task.citations else []

    if engine == "typst":
        try:
            from app.pipeline.export.typst_renderer import render_report_to_pdf

            pdf = render_report_to_pdf(clean_report, citations=citations_data)
        except Exception as typst_err:
            logger.exception("Typst render thất bại cho task %s, thử fallback HTML", task_id)
            try:
                from app.pipeline.export.pdf_renderer import report_to_pdf

                pdf = report_to_pdf(clean_report)
            except Exception as fallback_err:
                logger.exception("Fallback HTML render cũng thất bại")
                raise HTTPException(
                    status_code=500,
                    detail=f"Lỗi khi biên dịch PDF Typst: {typst_err}; fallback HTML: {fallback_err}",
                ) from fallback_err
    else:
        try:
            from app.pipeline.export.pdf_renderer import report_to_pdf

            pdf = report_to_pdf(clean_report)
        except Exception as exc:
            logger.exception("PDF (HTML/Chromium) render thất bại cho task %s", task_id)
            raise HTTPException(
                status_code=500,
                detail=f"Lỗi khi xuất PDF (Playwright/HTML): {exc}. Vui lòng thử ?engine=typst.",
            ) from exc

    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="paperai-{task_id[:8]}.pdf"'},
    )
