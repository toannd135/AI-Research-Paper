"""FastAPI app entrypoint, mount router các module."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.papers import router as papers_router
from app.api.routes.research import router as research_router
from app.api.routes.sources import router as sources_router
from app.core.config import get_settings

app = FastAPI(title=get_settings().app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers_router)
app.include_router(chat_router)
app.include_router(research_router)
app.include_router(sources_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
