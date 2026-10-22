"""Băm mật khẩu (bcrypt) và phát/giải mã JWT."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    # bcrypt chỉ xét 72 byte đầu; cắt tường minh để không lỗi với mật khẩu dài.
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: str, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": user_id, "role": role, "exp": expire}, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Trả về user id, hoặc None nếu token sai/hết hạn."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None
