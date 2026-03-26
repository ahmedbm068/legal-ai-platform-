from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str

    # Redis
    REDIS_URL: str

    # MinIO
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str

    class Config:
        env_file = ".env"


settings = Settings()