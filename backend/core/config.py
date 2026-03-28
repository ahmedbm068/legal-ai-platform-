from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # MinIO
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: str = "openai/gpt-4o-mini"
    SUMMARY_AGENT_MODEL: Optional[str] = None
    OPENROUTER_SITE_URL: Optional[str] = None
    OPENROUTER_APP_NAME: str = "legal-ai-platform"

    # Frontend
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
