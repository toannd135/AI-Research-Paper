"""POST /research, GET /research/{id}, GET /research/{id}/pdf."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.agent.clarify import clarify
from app.ai.llm_gateway.base import LLMGatewayError
from app.api.deps import can_access, get_current_user, get_current_user_or_query_token
from app.api.models.conversation import Conversation
from app.api.models.research_task import ResearchTask
from app.api.models.user import ROLE_ADMIN, User
from app.core.database import get_db
from app.core.schemas import (
    Citation,
    ResearchClarificationResponse,
    ResearchRequest,
    ResearchStatus,
    ResearchTaskResponse,
)
from app.pipeline.tasks import run_research

# Không đặt get_current_user ở cấp router: route /pdf nhận token qua ?access_token= (mở tab mới, không có header).
router = APIRouter(prefix="/research", tags=["research"])


@router.get("/", include_in_schema=False)
@router.get("")
def list_research(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: ResearchStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(ResearchTask)
    if user.role != ROLE_ADMIN:
        query = query.filter(ResearchTask.user_id == user.id)
    if status is not None:
        query = query.filter(ResearchTask.status == status.value)
    total = query.count()
    tasks = query.with_entities(
        ResearchTask.id, ResearchTask.question, ResearchTask.refined_question, ResearchTask.status,
        (ResearchTask.report.isnot(None) & (ResearchTask.report != "")).label("has_report"),
        ResearchTask.citations, ResearchTask.error, ResearchTask.created_at,
    ).order_by(ResearchTask.created_at.desc(), ResearchTask.id.desc()).offset(offset).limit(limit).all()
    return {
        "items": [{
            "id": task.id,
            "question": task.question,
            "refined_question": task.refined_question,
            "status": task.status,
            "has_report": task.has_report,
            "citation_count": len(json.loads(task.citations)) if task.citations else 0,
            "error": task.error,
            "created_at": task.created_at,
        } for task in tasks],
        "total": total, "limit": limit, "offset": offset,
    }


@router.post("/", response_model=ResearchTaskResponse | ResearchClarificationResponse)
def create_research(
    payload: ResearchRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    try:
        result = clarify(payload.question, payload.clarification_answers)
    except LLMGatewayError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if result["status"] == "needs_clarification":
        return ResearchClarificationResponse(questions=result["questions"])

    task = ResearchTask(
        question=payload.question,
        clarification_answers=json.dumps(payload.clarification_answers) if payload.clarification_answers else None,
        refined_question=result["refined_question"],
        audience=payload.audience,
        field=payload.field,
        status=ResearchStatus.PENDING.value,
        user_id=user.id,
    )
    db.add(task)
    db.commit()

    run_research.delay(task.id)

    return ResearchTaskResponse(
        id=task.id, question=task.question, refined_question=task.refined_question,
        status=ResearchStatus.PENDING, created_at=task.created_at,
    )


@router.get("/{task_id}", response_model=ResearchTaskResponse)
def get_research(
    task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ResearchTaskResponse:
    task = db.get(ResearchTask, task_id)
    if task is None or not can_access(user, task.user_id):
        raise HTTPException(status_code=404, detail="Research task không tồn tại")

    citations = [Citation(**c) for c in json.loads(task.citations)] if task.citations else []

    return ResearchTaskResponse(
        id=task.id,
        question=task.question,
        refined_question=task.refined_question,
        status=ResearchStatus(task.status),
        report=task.report,
        citations=citations,
        error=task.error,
        created_at=task.created_at,
    )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_research(
    task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    """Xoá phiên nghiên cứu (kể cả đang chạy) cùng hội thoại hỏi đáp gắn với nó."""
    task = db.get(ResearchTask, task_id)
    if task is None or not can_access(user, task.user_id):
        raise HTTPException(status_code=404, detail="Research task không tồn tại")
    for conversation in db.query(Conversation).filter(Conversation.research_task_id == task_id).all():
        db.delete(conversation)
    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{task_id}/pdf")
def export_research_pdf(
    task_id: str,
    engine: str = "html",
    columns: int = Query(default=2, ge=1, le=2),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_or_query_token),
) -> Response:
    task = db.get(ResearchTask, task_id)
    if task is None or not can_access(user, task.user_id):
        raise HTTPException(status_code=404, detail="Research task không tồn tại")
    if not task.report:
        raise HTTPException(status_code=409, detail="Research task chưa có báo cáo")

    from app.agent.format_sanitizer import sanitize_academic_markdown

    clean_report = sanitize_academic_markdown(task.report)
    citations_data = json.loads(task.citations) if task.citations else []

    if engine == "typst":
        try:
            from app.pipeline.export.typst_renderer import render_report_to_pdf

            pdf = render_report_to_pdf(clean_report, citations=citations_data)
        except Exception as e:
            logger.exception("Typst rendering failed for task %s: %s", task_id, e)
            try:
                from app.pipeline.export.pdf_renderer import report_to_pdf

                pdf = report_to_pdf(clean_report, columns=columns)
            except Exception as fallback_err:
                logger.exception("Fallback PDF rendering also failed: %s", fallback_err)
                raise HTTPException(
                    status_code=500,
                    detail=f"Lỗi khi biên dịch PDF Typst: {e}",
                )
    else:
        try:
            from app.pipeline.export.pdf_renderer import report_to_pdf

            pdf = report_to_pdf(clean_report, columns=columns)
        except Exception as e:
            logger.exception("PDF rendering failed for task %s: %s", task_id, e)
            raise HTTPException(
                status_code=500,
                detail=f"Lỗi khi xuất PDF (Playwright/HTML): {e}. Vui lòng thử ?engine=typst.",
            )

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="paperai-{task_id[:8]}.pdf"'},
    )

