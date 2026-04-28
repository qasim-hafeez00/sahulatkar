from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Dict


class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"
    TESTING: bool = False
    DB_DIALECT: str = "postgresql"  # "sqlite" for tests

    # DB
    DATABASE_URL: str = "postgresql+asyncpg://sk_app:password@localhost:5432/sahulatkar"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT Config
    JWT_PRIVATE_KEY: str = ""
    JWT_PUBLIC_KEY: str = ""
    JWT_ACCESS_TTL: int = 900      # 15 minutes
    JWT_REFRESH_TTL: int = 86400   # 24 hours

    # OTP
    OTP_TTL: int = 180             # 3 minutes
    MAX_OTP_ATTEMPTS: int = 3
    OTP_ATTEMPTS_TTL: int = 300    # 5 minutes

    # S3 Storage (Optional, fallback to LocalStorage if missing)
    S3_BUCKET: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None
    CONTRACT_STORAGE_DIR: str = "./tmp/contracts"

    # Notifications
    NOTIFICATION_SMS_ENABLED: bool = True
    ADMIN_DASHBOARD_CACHE_TTL: int = 60
    SECP_LICENSE_NUMBER: str = ""

    # Admin
    ADMIN_SESSION_TTL: int = 28800      # 8 hours
    ADMIN_RATE_LIMIT_PER_MIN: int = 30
    REQUIRE_ADMIN_MFA: bool = True
    ADMIN_ALLOWED_ORIGIN: str = "https://admin.sahulatkar.pk"
    # SEC-02: Comma-separated list of allowed IPs for admin login; empty = disabled
    ADMIN_IP_ALLOWLIST: str = ""

    # External payment webhooks
    JAZZCASH_WEBHOOK_SECRET: Optional[str] = None
    SAFEPAY_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    WEBHOOK_MAX_BODY_SIZE: int = 1_048_576

    # Inter-service security
    INTERNAL_SERVICE_TOKEN: str = "local-internal-token"

    # KMS — local mock path uses KMS_MOCK_KEY_HEX (AES-256 hex-encoded key).
    # Production: set ENVIRONMENT=production and KMS_KEY_ARN for AWS KMS Boto3 path.
    KMS_MOCK_KEY_HEX: str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    KMS_KEY_ARN: Optional[str] = None

    # Business rules
    COMPANY_LEGAL_NAME: str = "SahulatKar (Pvt) Ltd."
    MURABAHA_VALIDITY_DAYS: int = 3
    WAKALAH_VALIDITY_HOURS: int = 24
    MAX_ACTIVE_ORDERS_PER_USER: int = 5
    PROFIT_RATES: Dict[str, float] = {"3": 2.5, "4": 4.0, "6": 7.0, "12": 15.0}

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()


def validate_critical_settings() -> None:
    """Abort startup if production-critical config is still at insecure defaults."""
    if settings.ENVIRONMENT != "production":
        return
    errors = []
    if settings.KMS_MOCK_KEY_HEX == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef":
        errors.append("KMS_MOCK_KEY_HEX is set to the default insecure key — set KMS_KEY_ARN for production")
    if settings.INTERNAL_SERVICE_TOKEN == "local-internal-token":
        errors.append("INTERNAL_SERVICE_TOKEN is set to the default weak token — rotate it before production")
    if not settings.STRIPE_WEBHOOK_SECRET:
        errors.append("STRIPE_WEBHOOK_SECRET is required in production for Stripe webhook verification")
    if not settings.S3_BUCKET:
        errors.append("S3_BUCKET is required in production for contract PDF storage")
    if not settings.SECP_LICENSE_NUMBER:
        errors.append("SECP_LICENSE_NUMBER is required in production for regulatory compliance")
    if not settings.JWT_PRIVATE_KEY:
        errors.append("JWT_PRIVATE_KEY must be set in production")
    if errors:
        raise RuntimeError("PRODUCTION_CONFIG_VALIDATION_FAILED:\n" + "\n".join(f"  - {e}" for e in errors))
