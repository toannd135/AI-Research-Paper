"""Phạm vi paper mà truy xuất được phép nhìn thấy (theo chủ sở hữu).

Worker Celery (prefork) chạy mỗi lần một task trong mỗi tiến trình, nên một biến cấp module là đủ
và chia sẻ được cho các thread con của LangGraph (ContextVar thì không đảm bảo qua thread).
None = không giới hạn (admin / dữ liệu cũ không có chủ).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.models.paper import Paper
from app.api.models.user import ROLE_ADMIN, User

_allowed_paper_ids: set[str] | None = None


def set_allowed_paper_ids(ids: set[str] | None) -> None:
    global _allowed_paper_ids
    _allowed_paper_ids = ids


def get_allowed_paper_ids() -> set[str] | None:
    return _allowed_paper_ids


def allowed_paper_ids_for(db: Session, user: User | None) -> set[str] | None:
    """Tập id paper user được xem; None nếu không giới hạn."""
    if user is None or user.role == ROLE_ADMIN:
        return None
    return set(db.scalars(select(Paper.id).where(Paper.user_id == user.id)).all())


def filter_chunks(chunks: list, allowed: set[str] | None) -> list:
    if allowed is None:
        return chunks
    return [c for c in chunks if c.paper_id in allowed]
