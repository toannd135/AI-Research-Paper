"""Đọc .env: DATABASE_URL, QDRANT_URL, LLM keys..."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    hybrid_alpha: float = 0.7
    hybrid_beta: float = 0.3
    context_token_limit: int = 8000

    open_alex_api_url: str = "https://api.openalex.org"
    open_alex_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
