"""POST /research, GET /research/{id}."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.clarify import clarify
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
    result = clarify(payload.question, payload.clarification_answers)

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
