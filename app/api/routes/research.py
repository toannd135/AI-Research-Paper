"""POST /research, GET /research/{id}, GET /research/{id}/pdf."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

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
def export_research_pdf(task_id: str, db: Session = Depends(get_db)) -> Response:
    from app.pipeline.export.pdf_renderer import report_to_pdf

    task = db.get(ResearchTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Research task không tồn tại")
    if not task.report:
        raise HTTPException(status_code=409, detail="Research task chưa có báo cáo")

    pdf = report_to_pdf(task.report)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="paperai-{task_id[:8]}.pdf"'},
    )
