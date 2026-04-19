from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"
    
    # DB
    DATABASE_URL: str = "postgresql+asyncpg://sk_app:password@localhost:5432/sahulatkar"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT Config
    JWT_PRIVATE_KEY: str = ""
    JWT_PUBLIC_KEY: str = ""
    JWT_ACCESS_TTL: int = 900  # 15 minutes
    JWT_REFRESH_TTL: int = 86400  # 24 hours
    
    # OTP 
    OTP_TTL: int = 180  # 3 minutes
    MAX_OTP_ATTEMPTS: int = 3
    OTP_ATTEMPTS_TTL: int = 300  # 5 minutes

    # S3 Storage (Optional, fallback to LocalStorage if missing)
    S3_BUCKET: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None
    CONTRACT_STORAGE_DIR: str = "./tmp/contracts"

    # Notifications
    NOTIFICATION_SMS_ENABLED: bool = True
    
    # Admin
    ADMIN_SESSION_TTL: int = 28800  # 8 hours
    ADMIN_RATE_LIMIT_PER_MIN: int = 30  # per-admin IP rate cap
    REQUIRE_ADMIN_MFA: bool = True
    ADMIN_ALLOWED_ORIGIN: str = "https://admin.sahulatkar.pk"

    # External payment webhooks
    JAZZCASH_WEBHOOK_SECRET: Optional[str] = None
    SAFEPAY_WEBHOOK_SECRET: Optional[str] = None

    # Inter-service security (P4-3)
    INTERNAL_SERVICE_TOKEN: str = "local-internal-token"

    # KMS — local mock path uses KMS_MOCK_KEY_HEX (AES-256 hex-encoded key).
    # Production: set ENVIRONMENT=production and KMS_KEY_ARN for AWS KMS Boto3 path.
    KMS_MOCK_KEY_HEX: str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    KMS_KEY_ARN: Optional[str] = None  # e.g. arn:aws:kms:ap-south-1:123456789:key/xxxx

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

