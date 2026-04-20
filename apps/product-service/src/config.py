from typing import List, Literal
import logging
from decimal import Decimal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql+asyncpg://sk_app:password@localhost:5432/sahulatkar"
    # GAP-B FIX: explicit dialect flag avoids deprecated session.bind usage in SQLAlchemy 2.x.
    # Set to "sqlite" in test environments via conftest.py / environment variable.
    DATABASE_DIALECT: str = "postgresql"
    REDIS_URL: str = "redis://localhost:6379/1"
    REDIS_DB: int = 1

    FEATURE_RYE_ENABLED: bool = False
    FEATURE_VIOLET_ENABLED: bool = True
    FEATURE_GROQ_ENABLED: bool = True
    FEATURE_OPENAI_FALLBACK: bool = True
    FEATURE_HITL_ESCALATION: bool = True
    FEATURE_CHECKOUT_AGENT: bool = True
    FEATURE_CAPTCHA_SOLVING: bool = False

    RYE_API_URL: str = "https://api.rye.com/v1"
    RYE_API_KEY: str = ""
    VIOLET_API_URL: str = "https://api.violet.io"
    VIOLET_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    BRIGHTDATA_PROXY_URL: str = ""
    CAPTCHA_API_KEY: str = ""
    CAPTCHA_PROVIDER: Literal["two_captcha", "capsolver", "none"] = "none"
    FERNET_KEY: str = ""

    EXTRACTION_TIMEOUT_SECONDS: int = Field(default=45, ge=5, le=300)
    EXTRACTION_MAX_RETRIES: int = Field(default=2, ge=0, le=10)
    EXTRACTION_CONFIDENCE_THRESHOLD: float = Field(default=0.70, ge=0.0, le=1.0)
    FEATURE_STRICT_URL_HEAD_CHECK: bool = False
    CHECKOUT_TIMEOUT_SECONDS: int = Field(default=45, ge=5, le=600)
    CHECKOUT_MAX_RETRIES: int = Field(default=3, ge=0, le=20)
    CHECKOUT_RETRY_BACKOFF_SECONDS: float = Field(default=1.0, ge=0.1, le=60.0)
    PRICE_DRIFT_THRESHOLD_PCT: Decimal = Field(default=Decimal("5.0"), ge=Decimal("0"), le=Decimal("100"))
    HITL_SLA_MINUTES: int = Field(default=15, ge=1, le=1440)
    MIN_PRODUCT_PRICE_PKR: Decimal = Field(default=Decimal("1"), ge=Decimal("0"))
    MAX_PRODUCT_PRICE_PKR: Decimal = Field(default=Decimal("200000"), ge=Decimal("1"))
    PRODUCT_CACHE_TTL_SECONDS: int = Field(default=3600, ge=60, le=604800)
    # GAP-C: /extract endpoint rate limit (requests per minute per user/IP).
    EXTRACT_RATE_LIMIT_PER_MINUTE: int = Field(default=10, ge=1, le=1000)

    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_SCREENSHOTS: str = "sk-screenshots-dev"
    PRODUCT_IMAGE_BUCKET: str = "sk-product-images-dev"
    AWS_KMS_KEY_ARN: str = ""
    INTERNAL_SERVICE_TOKEN: str = "dev-secret-token"
    JWT_PUBLIC_KEY: str = ""

    INTERNAL_HTTP_CONNECT_TIMEOUT_SECONDS: float = Field(default=5.0, ge=0.1, le=30.0)
    INTERNAL_HTTP_READ_TIMEOUT_SECONDS: float = Field(default=30.0, ge=1.0, le=300.0)

    @model_validator(mode="after")
    def _validate_runtime_constraints(self):
        if self.MIN_PRODUCT_PRICE_PKR > self.MAX_PRODUCT_PRICE_PKR:
            raise ValueError("MIN_PRODUCT_PRICE_PKR cannot be greater than MAX_PRODUCT_PRICE_PKR")
        if self.ENVIRONMENT != "local" and self.INTERNAL_SERVICE_TOKEN == "dev-secret-token":
            raise ValueError("INTERNAL_SERVICE_TOKEN must be changed outside local environment")
        return self

    @property
    def cors_allow_origins_list(self) -> List[str]:
        if self.ENVIRONMENT == "local":
            return ["*"]
        return ["https://api.sahulatkar.com", "https://gateway.sahulatkar.internal"]

    CORS_ALLOW_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
