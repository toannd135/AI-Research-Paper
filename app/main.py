"""FastAPI app entrypoint, mount router các module."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, papers, research, sources
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers.router)
app.include_router(chat.router)
app.include_router(research.router)
app.include_router(sources.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
