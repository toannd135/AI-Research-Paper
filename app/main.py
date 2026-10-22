"""FastAPI app entrypoint, mount router các module."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, chat, papers, research, sources
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


def _seed_admin() -> None:
    try:
        with SessionLocal() as db:
            auth.ensure_admin(db)
    except Exception:  # DB chưa sẵn sàng/chưa migrate không được chặn API khởi động
        logger.exception("Không tạo được tài khoản admin ban đầu (đã chạy alembic upgrade head chưa?)")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    if settings.env != "local" and settings.jwt_secret.startswith("dev-only"):
        logger.error("JWT_SECRET đang là giá trị mặc định — hãy đặt JWT_SECRET riêng trước khi triển khai")
    _seed_admin()
    logger.info("paperai API khởi động (env=%s, upload_dir=%s)", settings.env, settings.upload_dir)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Paper research assistant: upload PDF -> hybrid RAG chat -> deep research agent có citation.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(papers.router)
app.include_router(chat.router)
app.include_router(research.router)
app.include_router(sources.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Không để traceback thô lọt ra client; log đầy đủ phía server."""
    logger.exception("Lỗi chưa xử lý tại %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Lỗi máy chủ nội bộ: {type(exc).__name__}"})


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}
