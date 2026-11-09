"""Nhập PDF có sẵn trong upload_dir (chưa có record DB) và đưa vào pipeline; chạy lặp lại an toàn."""

import hashlib
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.models.paper import Paper
from app.api.models.user import ROLE_ADMIN, User
from app.api.models.workspace import Workspace
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


def assign_papers_to_user(
    db: Session, directory: Path, email: str, apply: bool = False, workspace_name: str | None = None
) -> list[Paper]:
    """Gán chủ sở hữu (`user_id`) và (tuỳ chọn) workspace cho paper có PDF nằm trực tiếp trong `directory`.

    Trả về các paper sẽ/đã đổi. Chỉ ghi `user_id`/`workspace_id`; `workspace_name` được tạo nếu user chưa có.
    `apply=False` chỉ liệt kê (dry-run, không tạo workspace).
    """
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise ValueError(f"Không có người dùng {email!r}; hãy đăng ký trước.")
    folder = directory.resolve()
    workspace = None
    if workspace_name:
        workspace = db.scalar(select(Workspace).where(Workspace.user_id == user.id, Workspace.name == workspace_name))
        if workspace is None and apply:
            workspace = Workspace(user_id=user.id, name=workspace_name)
            db.add(workspace)
            db.flush()
    target_ws = workspace.id if workspace else None
    changed = [
        p
        for p in db.scalars(select(Paper))
        if Path(p.file_path).resolve().parent == folder
        and (p.user_id != user.id or (workspace_name and p.workspace_id != target_ws))
    ]
    if apply:
        for p in changed:
            p.user_id = user.id
            if workspace_name:
                p.workspace_id = target_ws
        db.commit()
    return changed


def foreign_citation_ids(db: Session, citation_paper_ids: list[str], directory: Path) -> list[str]:
    """Các paper_id được trích dẫn nhưng KHÔNG phải paper `done` có PDF nằm trong `directory` (nguồn ngoài/sai đề tài)."""
    folder = directory.resolve()
    allowed = {
        p.id
        for p in db.scalars(select(Paper).where(Paper.status == PaperStatus.DONE.value))
        if Path(p.file_path).resolve().parent == folder
    }
    return [pid for pid in dict.fromkeys(citation_paper_ids) if pid not in allowed]
