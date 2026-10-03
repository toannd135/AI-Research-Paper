"""POST /papers/upload, GET /papers/{id}..."""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.models.paper import Paper
from app.core.database import get_db
from app.core.schemas import PaperStatus, PaperStatusResponse, PaperUploadResponse
from app.pipeline.tasks import process_paper

router = APIRouter(prefix="/papers", tags=["papers"])

UPLOAD_DIR = Path("data/papers")


@router.post("/upload", response_model=PaperUploadResponse)
def upload_paper(file: UploadFile, db: Session = Depends(get_db)) -> PaperUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    paper_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{paper_id}.pdf"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    paper = Paper(id=paper_id, filename=file.filename, file_path=str(dest), status=PaperStatus.PENDING.value)
    db.add(paper)
    db.commit()

    process_paper.delay(paper_id)

    return PaperUploadResponse(id=paper.id, filename=paper.filename, status=PaperStatus.PENDING)


@router.get("/{paper_id}", response_model=PaperStatusResponse)
def get_paper(paper_id: str, db: Session = Depends(get_db)) -> PaperStatusResponse:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper không tồn tại")
    return PaperStatusResponse(
        id=paper.id,
        filename=paper.filename,
        status=PaperStatus(paper.status),
        error=paper.error,
        created_at=paper.created_at,
    )
