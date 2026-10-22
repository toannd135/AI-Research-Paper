"""Nhập PDF có sẵn trong upload_dir (chưa có record DB) và đưa vào pipeline; chạy lặp lại an toàn."""

import hashlib
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.models.paper import Paper
from app.api.models.user import ROLE_ADMIN, User
from app.core.config import get_settings
from app.core.schemas import PaperStatus
from app.pipeline.tasks import process_paper

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _stem_as_id(path: Path) -> str:
    try:
        return str(uuid.UUID(path.stem))
    except ValueError:
        return str(uuid.uuid4())


def import_existing_papers(db: Session) -> int:
    """Tạo record cho mỗi PDF chưa có (theo đường dẫn hoặc sha256), gán cho admin; trả về số paper mới."""
    upload_dir = Path(get_settings().upload_dir)
    if not upload_dir.is_dir():
        return 0

    known_paths = set(db.scalars(select(Paper.file_path)))
    known_hashes = set(db.scalars(select(Paper.content_hash).where(Paper.content_hash.is_not(None))))
    admin_email = (get_settings().admin_email or "").strip().lower()
    owner = db.scalar(select(User).where(User.email == admin_email)) if admin_email else None
    owner = owner or db.scalar(select(User).where(User.role == ROLE_ADMIN).limit(1))

    created: list[str] = []
    for pdf in sorted(upload_dir.glob("*.pdf")):
        if str(pdf) in known_paths:
            continue
        digest = _sha256(pdf)
        if digest in known_hashes:
            continue
        known_hashes.add(digest)
        paper_id = _stem_as_id(pdf)
        if db.get(Paper, paper_id) is not None:
            paper_id = str(uuid.uuid4())
        db.add(
            Paper(
                id=paper_id,
                filename=pdf.name[:255],
                file_path=str(pdf),
                content_hash=digest,
                status=PaperStatus.PENDING.value,
                user_id=owner.id if owner else None,
            )
        )
        created.append(paper_id)
    db.commit()

    for paper_id in created:
        try:
            process_paper.delay(paper_id)
        except Exception:  # broker chưa sẵn sàng: paper ở trạng thái pending, có thể /reprocess sau
            logger.warning("Không đẩy được paper %s vào hàng đợi (broker chưa sẵn sàng?)", paper_id)
    if created:
        logger.info("Đã nhập %d PDF có sẵn trong %s", len(created), upload_dir)
    return len(created)
