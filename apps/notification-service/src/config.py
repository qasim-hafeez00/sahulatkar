from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://sk_app:password@localhost:5432/sahulatkar"
    REDIS_URL: str = "redis://localhost:6379/5"
    REDIS_DB: int = 5

    AFTERSHIP_API_KEY: str = ""
    AFTERSHIP_WEBHOOK_SECRET: str = ""
    AFTERSHIP_BASE_URL: str = "https://api.aftership.com/v4"

    INTERNAL_API_KEY: str = "test-key"
    SERVICE_NAME: str = "notification-service"
    LOG_LEVEL: str = "INFO"

    CORS_ALLOW_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
