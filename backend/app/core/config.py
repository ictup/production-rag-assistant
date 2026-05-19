from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "production-rag-assistant"
    app_version: str = "0.1.0"
    env: str = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_keys: str = "dev-key"
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"
    sync_database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/rag"
    embedding_provider: Literal["fake", "openai"] = "fake"
    embedding_model: str = "fake-embedding"
    embedding_dimension: int = 1536
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2
    openai_retry_delay_seconds: float = 0.25
    openai_max_output_tokens: int = 512
    cors_allowed_origins: str = ""
    cors_allowed_origin_regex: str | None = None
    cors_allow_credentials: bool = False
    rate_limit_enabled: bool = False
    rate_limit_requests: int = Field(default=60, gt=0)
    rate_limit_window_seconds: float = Field(default=60.0, gt=0)
    rate_limit_excluded_paths: str = (
        "/health,/metrics,/app,/openapi.json,/docs,/redoc"
    )
    reranker_provider: Literal["none"] = "none"
    rerank_top_n: int = 5
    vector_top_k: int = 20
    sparse_top_k: int = 20
    fused_top_k: int = 20
    rrf_k: int = 60
    generator_provider: Literal["fake", "openai"] = "fake"
    llm_model: str = "fake-llm"
    refusal_score_threshold: float = 0.01


@lru_cache
def get_settings() -> Settings:
    return Settings()
