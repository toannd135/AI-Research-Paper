"""POST /research, GET /research/{id}, GET /research/{id}/pdf."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.agent.clarify import clarify
from app.ai.llm_gateway.base import LLMGatewayError
from app.api.models.research_task import ResearchTask
from app.core.database import get_db
from app.core.schemas import (
    Citation,
    ResearchClarificationResponse,
    ResearchRequest,
    ResearchStatus,
    ResearchTaskResponse,
)
from app.pipeline.tasks import run_research

router = APIRouter(prefix="/research", tags=["research"])


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
        clarification_answers=json.dumps(payload.clarification_answers) if payload.clarification_answers else None,
        refined_question=result["refined_question"],
        status=ResearchStatus.PENDING.value,
    )
    db.add(task)
    db.commit()

    run_research.delay(task.id)

    return ResearchTaskResponse(id=task.id, status=ResearchStatus.PENDING, created_at=task.created_at)


@router.get("/{task_id}", response_model=ResearchTaskResponse)
def get_research(task_id: str, db: Session = Depends(get_db)) -> ResearchTaskResponse:
    task = db.get(ResearchTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Research task không tồn tại")

    citations = [Citation(**c) for c in json.loads(task.citations)] if task.citations else []

    return ResearchTaskResponse(
        id=task.id,
        status=ResearchStatus(task.status),
        report=task.report,
        citations=citations,
        error=task.error,
        created_at=task.created_at,
    )


@router.get("/{task_id}/pdf")
def export_research_pdf(
    task_id: str,
    engine: str = "typst",
    db: Session = Depends(get_db),
) -> Response:
    task = db.get(ResearchTask, task_id)
    if task is None:
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

                pdf = report_to_pdf(clean_report)
            except Exception as fallback_err:
                logger.exception("Fallback PDF rendering also failed: %s", fallback_err)
                raise HTTPException(
                    status_code=500,
                    detail=f"Lỗi khi biên dịch PDF Typst: {e}",
                )
    else:
        try:
            from app.pipeline.export.pdf_renderer import report_to_pdf

            pdf = report_to_pdf(clean_report)
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

