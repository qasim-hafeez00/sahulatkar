from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql+asyncpg://sk_app:password@localhost:5432/sahulatkar"
    REDIS_URL: str = "redis://localhost:6379/1"
    REDIS_DB: int = 1

    FEATURE_RYE_ENABLED: bool = False
    FEATURE_GROQ_ENABLED: bool = True
    FEATURE_OPENAI_FALLBACK: bool = True
    FEATURE_HITL_ESCALATION: bool = True
    FEATURE_CHECKOUT_AGENT: bool = True

    RYE_API_URL: str = "https://api.rye.com/v1"
    RYE_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    BRIGHTDATA_PROXY_URL: str = ""
    FERNET_KEY: str = ""

    EXTRACTION_TIMEOUT_SECONDS: int = 45
    EXTRACTION_MAX_RETRIES: int = 2
    CHECKOUT_TIMEOUT_SECONDS: int = 45
    CHECKOUT_MAX_RETRIES: int = 3
    HITL_SLA_MINUTES: int = 15

    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_SCREENSHOTS: str = "sk-screenshots-dev"
    INTERNAL_SERVICE_TOKEN: str = "dev-secret-token"
    JWT_PUBLIC_KEY: str = ""

    @property
    def cors_allow_origins_list(self) -> List[str]:
        if self.ENVIRONMENT == "local":
            return ["*"]
        return ["https://api.sahulatkar.com", "https://gateway.sahulatkar.internal"]

    CORS_ALLOW_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
