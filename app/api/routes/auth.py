"""POST /auth/register, POST /auth/login, GET /auth/me, quản lý người dùng (admin)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.api.models.user import ROLE_ADMIN, ROLE_USER, ROLES, User
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)


class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role, is_active=user.is_active)


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(access_token=create_access_token(user.id, user.role), user=_out(user))


DEV_ADMIN_EMAIL = "admin@gmail.com"
DEV_ADMIN_PASSWORD = "admin"


def _find_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def ensure_admin(db: Session) -> None:
    """Tạo admin ban đầu từ ADMIN_EMAIL/ADMIN_PASSWORD nếu chưa có."""
    settings = get_settings()
    email, password = settings.admin_email, settings.admin_password
    if not email and not password and settings.env == "local":
        # Máy dev: pull code về là đăng nhập được ngay. Môi trường khác bắt buộc đặt ADMIN_EMAIL/ADMIN_PASSWORD.
        email, password = DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD
        logger.warning("ENV=local và chưa đặt ADMIN_EMAIL/ADMIN_PASSWORD: dùng admin mặc định %s", email)
    if not email or not password:
        return
    if _find_by_email(db, email) is not None:
        return
    db.add(
        User(
            email=email.strip().lower(),
            full_name="Administrator",
            password_hash=hash_password(password),
            role=ROLE_ADMIN,
        )
    )
    db.commit()
    logger.info("Đã tạo tài khoản admin %s", email)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    if not get_settings().allow_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hệ thống đang tắt đăng ký tự do")
    if _find_by_email(db, payload.email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email đã được đăng ký")
    # Tài khoản tự đăng ký luôn là user; chỉ admin mới nâng quyền được.
    user = User(
        email=payload.email.strip().lower(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=ROLE_USER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = _find_by_email(db, payload.email)
    # Cùng một thông báo cho sai email và sai mật khẩu để không lộ email nào tồn tại.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email hoặc mật khẩu không đúng")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị khoá")
    return _auth_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _out(user)


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[UserOut]:
    return [_out(u) for u in db.scalars(select(User).order_by(User.created_at.desc())).all()]


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str, payload: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")
    if payload.role is not None and payload.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"Vai trò phải là một trong {', '.join(ROLES)}")

    demoting = (payload.role is not None and payload.role != ROLE_ADMIN) or payload.is_active is False
    if user.role == ROLE_ADMIN and demoting:
        other_admins = db.scalar(
            select(func.count()).select_from(User).where(
                User.role == ROLE_ADMIN, User.is_active.is_(True), User.id != user.id
            )
        )
        if not other_admins:
            raise HTTPException(status_code=409, detail="Phải còn ít nhất một quản trị viên đang hoạt động")

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return _out(user)
