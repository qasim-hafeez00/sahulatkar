from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql+asyncpg://sk_app:password@localhost:5432/sahulatkar"
    REDIS_URL: str = "redis://localhost:6379/3"
    REDIS_DB: int = 3

    JWT_PUBLIC_KEY: str = ""
    JWT_PRIVATE_KEY: str = ""

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    SAFEPAY_API_KEY: str = ""
    SAFEPAY_API_SECRET: str = ""
    JAZZCASH_MERCHANT_ID: str = ""
    JAZZCASH_PASSWORD: str = ""
    VCN_ENCRYPTION_KEY: str = ""

    PAYMENT_CURRENCY: str = "PKR"
    DOWN_PAYMENT_MIN_PCT: float = 25.0
    DOWN_PAYMENT_MAX_PCT: float = 40.0
    VCN_BUFFER_PCT: float = 5.0
    VCN_EXPIRY_HOURS: int = 24

    CORS_ALLOW_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()