"""Dependency xác thực / phân quyền dùng chung cho các route."""

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.models.user import ROLE_ADMIN, User
from app.core.database import get_db
from app.core.security import decode_access_token


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer_token(request)
    user_id = decode_access_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa đăng nhập hoặc phiên đã hết hạn",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_or_query_token(
    request: Request, access_token: str | None = Query(default=None), db: Session = Depends(get_db)
) -> User:
    """Như get_current_user nhưng nhận thêm ?access_token= (cho link mở tab mới như xuất PDF)."""
    token = _bearer_token(request) or access_token
    user_id = decode_access_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chưa đăng nhập hoặc phiên đã hết hạn")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ quản trị viên mới có quyền này")
    return user


def can_access(user: User, owner_id: str | None) -> bool:
    """Admin xem được mọi dữ liệu; user chỉ xem dữ liệu của chính mình."""
    return user.role == ROLE_ADMIN or (owner_id is not None and owner_id == user.id)
