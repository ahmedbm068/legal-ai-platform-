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
    TRANSCRIPTION_API_KEY: Optional[str] = None
    TRANSCRIPTION_BASE_URL: Optional[str] = None
    TRANSCRIPTION_MODEL: str = "gpt-4o-mini-transcribe"
    LOCAL_TRANSCRIPTION_MODEL: str = "openai/whisper-tiny"
    TRANSCRIPTION_REMOTE_ENABLED: bool = True
    OPENROUTER_SITE_URL: Optional[str] = None
    OPENROUTER_APP_NAME: str = "legal-ai-platform"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_ENABLED: bool = True

    # Frontend
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"

    # Client portal email
    CLIENT_PORTAL_FIRM_NAME: str = "Arbi Mostaissier"
    PORTAL_EMAIL_FROM: str = "arbimostaisser@gmail.com"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    PORTAL_LOGIN_CODE_EXPIRE_MINUTES: int = 10
    PORTAL_ALLOW_CONSOLE_CODE_FALLBACK: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
