"""Đọc .env: DATABASE_URL, QDRANT_URL, LLM keys... Xem .env.example để biết đầy đủ biến."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

AgentProvider = Literal["openrouter", "groq", "gemini", "anthropic", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "paperai"
    env: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://paperai:paperai@localhost:5433/paperai"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "paper_chunks"

    redis_url: str = "redis://localhost:6380/0"
    celery_broker_url: str = "redis://localhost:6380/0"
    celery_result_backend: str = "redis://localhost:6380/1"

    # --- LLM providers ---
    gemini_api_key: str = ""
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    openrouter_api_key: str | None = None
    openrouter_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    openrouter_fallback_models: list[str] = [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "google/gemma-4-31b-it:free",
        "qwen/qwen3.8-27b:free",
    ]
    # Ép research agent dùng 1 provider; None = tự chọn theo key có sẵn.
    agent_provider: AgentProvider | None = None

    # --- Embedding / rerank ---
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    # auto = tự dò GPU (kiểm tra VRAM trống) rồi mới lùi về CPU; hoặc đặt cứng cpu|cuda|cuda:0|mps
    embedding_device: str = "auto"
    embedding_cache_ttl_seconds: int = 30 * 24 * 3600  # 0 = không hết hạn

    # --- Retrieval ---
    hybrid_alpha: float = 0.7
    hybrid_beta: float = 0.3
    context_token_limit: int = 8000

    # --- Upload ---
    max_upload_mb: int = 50
    upload_dir: str = "data/papers"

    # --- External sources ---
    open_alex_api_url: str = "https://api.openalex.org"
    open_alex_api_key: str | None = None

    # --- PDF export ---
    mermaid_ink_enabled: bool = True

    # Origin được phép gọi API trực tiếp (khi không đi qua Vite proxy), phân tách bằng dấu phẩy
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
