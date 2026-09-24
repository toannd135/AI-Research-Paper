"""Đọc .env: DATABASE_URL, QDRANT_URL, LLM keys..."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    app_name: str = "paperai"
    env: str = "local"
    log_level: str = "INFO"
    # Origin được phép gọi API trực tiếp (khi không đi qua Vite proxy), phân tách bằng dấu phẩy
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Database ---
    database_url: str = "postgresql+psycopg://paperai:paperai@localhost:5432/paperai"

    # --- Vector store ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "paper_chunks"

    # --- Celery / Redis ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # --- LLM providers ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    vllm_base_url: str = "http://localhost:8000/v1"

    # --- Embedding / rerank ---
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # --- Retrieval ---
    hybrid_alpha: float = 0.7
    hybrid_beta: float = 0.3
    context_token_limit: int = 8000

    # --- External sources (OpenAlex) ---
    openalex_base_url: str = "https://api.openalex.org"
    # Email gửi kèm request để vào "polite pool" của OpenAlex (khuyến nghị, không bắt buộc)
    openalex_mailto: str = ""
    openalex_timeout: float = 20.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
