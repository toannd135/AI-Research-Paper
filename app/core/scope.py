"""Phạm vi paper mà truy xuất được phép nhìn thấy (theo chủ sở hữu và workspace/đề tài).

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


_local_only: bool = False


def set_local_only(value: bool) -> None:
    """Task thuộc workspace: chỉ dùng PDF của workspace, tuyệt đối không gọi nguồn ngoài (OpenAlex)."""
    global _local_only
    _local_only = value


def is_local_only() -> bool:
    """Task đang chạy trong một kho (workspace)."""
    return _local_only


def external_search_allowed() -> bool:
    from app.core.config import get_settings

    return get_settings().external_search_enabled and not _local_only


def get_allowed_paper_ids() -> set[str] | None:
    return _allowed_paper_ids


def allowed_paper_ids_for(db: Session, user: User | None, workspace_id: str | None = None) -> set[str] | None:
    """Tập id paper được xem; None nếu không giới hạn.

    - Có `workspace_id`: chỉ paper của workspace đó (route đã kiểm quyền sở hữu workspace).
    - Không có: admin xem tất cả; user thường chỉ thấy paper CHƯA gán workspace, để paper của
      một đề tài không rò sang lượt chạy không chỉ định phiên.
    """
    if workspace_id:
        return set(db.scalars(select(Paper.id).where(Paper.workspace_id == workspace_id)).all())
    if user is None or user.role == ROLE_ADMIN:
        return None
    return set(db.scalars(select(Paper.id).where(Paper.user_id == user.id, Paper.workspace_id.is_(None))).all())


def filter_chunks(chunks: list, allowed: set[str] | None) -> list:
    if allowed is None:
        return chunks
    return [c for c in chunks if c.paper_id in allowed]
