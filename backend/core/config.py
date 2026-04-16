from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    PORTAL_SECRET_KEY: Optional[str] = None

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_TTL_SECONDS: int = 300
    LEGAL_SEARCH_CACHE_TTL_SECONDS: int = 900

    # MinIO
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str
    MINIO_SECURE: bool = False

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: str = "openai/gpt-4o-mini"
    LLM_SMALL_MODEL: Optional[str] = None
    LLM_STANDARD_MODEL: Optional[str] = None
    LLM_HEAVY_MODEL: Optional[str] = None
    VISION_MODEL: Optional[str] = None
    VISION_API_KEY: Optional[str] = None
    VISION_BASE_URL: Optional[str] = None
    SUMMARY_AGENT_MODEL: Optional[str] = None
    LLM_TIMEOUT_SECONDS: int = 45
    LLM_MAX_RETRIES: int = 2
    EXTERNAL_RESEARCH_ENABLED: bool = True
    EXTERNAL_RESEARCH_PROVIDER: str = "tavily"
    EXTERNAL_RESEARCH_MAX_RESULTS: int = 5
    EXTERNAL_RESEARCH_TIMEOUT_SECONDS: int = 20
    TAVILY_API_KEY: Optional[str] = None
    SERPAPI_API_KEY: Optional[str] = None
    TRANSCRIPTION_API_KEY: Optional[str] = None
    TRANSCRIPTION_BASE_URL: Optional[str] = None
    TRANSCRIPTION_MODEL: str = "gpt-4o-mini-transcribe"
    SPEECHMATICS_API_KEY: Optional[str] = None
    SPEECHMATICS_BASE_URL: str = "https://asr.api.speechmatics.com/v2"
    SPEECHMATICS_LANGUAGE: str = "en"
    SPEECHMATICS_ENABLE_AUTODETECT: bool = True
    SPEECHMATICS_POLL_INTERVAL_SECONDS: int = 2
    SPEECHMATICS_MAX_WAIT_SECONDS: int = 240
    LOCAL_TRANSCRIPTION_MODEL: str = "openai/whisper-tiny"
    TRANSCRIPTION_DEVICE: str = "auto"
    LOCAL_TRANSCRIPTION_PREFER_LOCAL_FILES: bool = True
    TRANSCRIPTION_PREWARM_ON_STARTUP: bool = True
    TRANSCRIPTION_REMOTE_ENABLED: bool = True
    OPENROUTER_SITE_URL: Optional[str] = None
    OPENROUTER_APP_NAME: str = "legal-ai-platform"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_ENABLED: bool = True
    RETRIEVAL_LEXICAL_WEIGHT: float = 0.4
    RETRIEVAL_SEMANTIC_WEIGHT: float = 0.6
    RETRIEVAL_MIN_SCORE: float = 0.05
    RETRIEVAL_FILTER_NON_LEGAL_TEST: bool = True
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 180
    SCANNED_PDF_MAX_PAGES: int = 80
    SCANNED_PDF_RENDER_SCALE: float = 2.0
    SCANNED_PDF_MIN_NATIVE_TEXT_CHARS: int = 240

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
    SMTP_TIMEOUT_SECONDS: int = 20
    PORTAL_LOGIN_CODE_EXPIRE_MINUTES: int = 10
    PORTAL_ALLOW_CONSOLE_CODE_FALLBACK: bool = True
    PORTAL_REQUIRE_TENANT_SLUG: bool = True
    STAFF_INVITE_ONLY: bool = True

    # Auth hardening
    AUTH_LOGIN_MAX_ATTEMPTS: int = 6
    AUTH_LOGIN_WINDOW_SECONDS: int = 300
    AUTH_LOGIN_BLOCK_SECONDS: int = 900
    PORTAL_LOGIN_MAX_ATTEMPTS: int = 6
    PORTAL_LOGIN_WINDOW_SECONDS: int = 300
    PORTAL_LOGIN_BLOCK_SECONDS: int = 900
    PORTAL_VERIFY_MAX_ATTEMPTS: int = 8
    PORTAL_VERIFY_WINDOW_SECONDS: int = 300
    PORTAL_VERIFY_BLOCK_SECONDS: int = 900

    # Upload controls
    DOCUMENT_UPLOAD_MAX_MB: int = 20
    VOICE_UPLOAD_MAX_MB: int = 25
    IMAGE_UPLOAD_MAX_MB: int = 12
    IMAGE_BATCH_MAX_FILES: int = 20
    VISION_MAX_ATTACHMENTS: int = 4

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
