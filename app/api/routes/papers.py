"""POST /papers/upload, GET /papers, GET /papers/{id}, DELETE /papers/{id}, POST /papers/{id}/reprocess."""

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import can_access, get_current_user
from app.api.models.paper import Paper
from app.api.models.user import ROLE_ADMIN, User
from app.core.config import get_settings
from app.core.database import get_db
from app.core.schemas import PaperListResponse, PaperStatus, PaperStatusResponse, PaperUploadResponse
from app.pipeline.figures import figures_dir
from app.pipeline.tasks import process_paper

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/papers", tags=["papers"], dependencies=[Depends(get_current_user)])

_PDF_MAGIC = b"%PDF"
_CHUNK_SIZE = 1024 * 1024


def _upload_dir() -> Path:
    path = Path(get_settings().upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _to_response(paper: Paper) -> PaperStatusResponse:
    return PaperStatusResponse(
        id=paper.id,
        filename=paper.filename,
        status=PaperStatus(paper.status),
        error=paper.error,
        created_at=paper.created_at,
    )


def _save_pdf(file: UploadFile, dest: Path) -> None:
    """Ghi file theo từng khối, kiểm tra magic bytes và giới hạn dung lượng (không đọc cả file vào RAM)."""
    limit = get_settings().max_upload_bytes
    written = 0
    head = file.file.read(len(_PDF_MAGIC))
    if head[: len(_PDF_MAGIC)] != _PDF_MAGIC:
        raise HTTPException(status_code=400, detail="File không phải PDF hợp lệ (thiếu header %PDF)")
    try:
        with dest.open("wb") as out:
            out.write(head)
            written += len(head)
            while chunk := file.file.read(_CHUNK_SIZE):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File vượt quá giới hạn {get_settings().max_upload_mb} MB",
                    )
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise


@router.post("/upload", response_model=PaperUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_paper(
    file: UploadFile, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PaperUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF")

    paper_id = str(uuid.uuid4())
    dest = _upload_dir() / f"{paper_id}.pdf"
    _save_pdf(file, dest)

    # Chỉ giữ tên file gốc (bỏ đường dẫn client gửi kèm), cắt theo độ dài cột.
    safe_name = Path(file.filename).name[:255]
    paper = Paper(
        id=paper_id, filename=safe_name, file_path=str(dest), status=PaperStatus.PENDING.value, user_id=user.id
    )
    db.add(paper)
    db.commit()

    process_paper.delay(paper_id)
    logger.info("Đã nhận paper %s (%s), đẩy vào upload_queue", paper_id, safe_name)

    return PaperUploadResponse(id=paper.id, filename=paper.filename, status=PaperStatus.PENDING)


@router.get("", response_model=PaperListResponse)
def list_papers(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: PaperStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaperListResponse:
    stmt = select(Paper)
    count_stmt = select(func.count()).select_from(Paper)
    if user.role != ROLE_ADMIN:
        stmt = stmt.where(Paper.user_id == user.id)
        count_stmt = count_stmt.where(Paper.user_id == user.id)
    if status_filter is not None:
        stmt = stmt.where(Paper.status == status_filter.value)
        count_stmt = count_stmt.where(Paper.status == status_filter.value)

    total = db.scalar(count_stmt) or 0
    papers = db.scalars(stmt.order_by(Paper.created_at.desc()).limit(limit).offset(offset)).all()
    return PaperListResponse(items=[_to_response(p) for p in papers], total=total, limit=limit, offset=offset)


@router.get("/{paper_id}", response_model=PaperStatusResponse)
def get_paper(
    paper_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PaperStatusResponse:
    paper = db.get(Paper, paper_id)
    if paper is None or not can_access(user, paper.user_id):
        raise HTTPException(status_code=404, detail="Paper không tồn tại")
    return _to_response(paper)


@router.post("/{paper_id}/reprocess", response_model=PaperStatusResponse)
def reprocess_paper(
    paper_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PaperStatusResponse:
    """Chạy lại pipeline parse→chunk→embed cho paper (vd: sau khi sửa lỗi parser)."""
    paper = db.get(Paper, paper_id)
    if paper is None or not can_access(user, paper.user_id):
        raise HTTPException(status_code=404, detail="Paper không tồn tại")
    if paper.status == PaperStatus.PROCESSING.value:
        raise HTTPException(status_code=409, detail="Paper đang được xử lý")
    if not Path(paper.file_path).exists():
        raise HTTPException(status_code=410, detail="File PDF gốc không còn trên đĩa")

    paper.status = PaperStatus.PENDING.value
    paper.error = None
    db.commit()
    process_paper.delay(paper_id)
    return _to_response(paper)


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(
    paper_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    """Xoá paper: vector trong Qdrant, file PDF trên đĩa và record DB."""
    from app.pipeline.vector_store.qdrant_client import delete_paper as delete_vectors

    paper = db.get(Paper, paper_id)
    if paper is None or not can_access(user, paper.user_id):
        raise HTTPException(status_code=404, detail="Paper không tồn tại")

    try:
        delete_vectors(paper_id)
    except Exception as exc:  # Qdrant lỗi không nên chặn việc xoá record
        logger.warning("Không xoá được vector của paper %s trong Qdrant: %s", paper_id, exc)

    Path(paper.file_path).unlink(missing_ok=True)
    shutil.rmtree(figures_dir(paper_id), ignore_errors=True)
    db.delete(paper)
    db.commit()
    logger.info("Đã xoá paper %s", paper_id)
