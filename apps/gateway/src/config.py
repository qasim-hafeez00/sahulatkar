import logging
import os
from typing import Optional, Dict

from pydantic_settings import BaseSettings, SettingsConfigDict

from sk_shared.boot_validation import raise_if_placeholder_credentials
from sk_shared.secrets_manager import SecretsManagerLoadError, load_secrets_manager_overrides

logger = logging.getLogger(__name__)


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

    # Comma-separated list of allowed CORS origins; empty = use production defaults
    # (plus localhost dev origins when ENVIRONMENT != "production")
    CORS_ORIGINS: str = ""

    # External payment webhooks
    JAZZCASH_WEBHOOK_SECRET: Optional[str] = None
    SAFEPAY_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    WEBHOOK_MAX_BODY_SIZE: int = 1_048_576

    # Inter-service security
    INTERNAL_SERVICE_TOKEN: str = "local-internal-token"

    # Product Service base URL — used to proxy the customer-facing checkout-agent
    # live-status stream (GET /orders/{id}/agent-status) through to Product
    # Service's internal SSE endpoint. Port 8001 per the service port table in
    # README.md.
    PRODUCT_SERVICE_BASE_URL: str = "http://localhost:8001"

    # Shared secret with notification-service. Used to sign the short-lived
    # X-Admin-Assertion header (see sk_shared.security.create_signed_assertion) that
    # propagates an already-authenticated admin's id/role/permissions to
    # notification-service's admin_notifications/admin_tracking routes, instead of
    # letting a direct caller set X-Admin-Role/X-Admin-Permissions itself. Must match
    # notification-service's INTERNAL_API_KEY setting. Also sent verbatim as
    # X-Internal-Key on POST /internal/notifications/otp (see
    # InternalServiceClient.send_otp) — that endpoint checks it directly via
    # require_internal_key, no assertion wrapping needed.
    INTERNAL_API_KEY: str = "test-key"

    # Base URL for notification-service — used to actually dispatch OTP SMS
    # (registration, login resend, password reset, contract signing) via
    # POST /api/v1/internal/notifications/otp. See InternalServiceClient.send_otp.
    NOTIFICATION_SERVICE_URL: str = "http://localhost:8005"

    # KMS — local mock path uses KMS_MOCK_KEY_HEX (AES-256 hex-encoded key).
    # Production: set ENVIRONMENT=production and KMS_KEY_ARN for AWS KMS Boto3 path.
    KMS_MOCK_KEY_HEX: str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    KMS_KEY_ARN: Optional[str] = None

    # CNIC identity verification. "mock" (default) uses a realistic
    # deterministic simulator with no external calls — safe for local/staging.
    # Set to "verisys" once NADRA Verisys enterprise onboarding is complete;
    # see src/services/nadra/verisys_provider.py. No other code changes
    # needed — src/services/kyc.py resolves the provider via
    # get_nadra_provider() and only ever calls the shared verify_cnic()
    # contract.
    NADRA_PROVIDER: str = "mock"
    NADRA_API_URL: Optional[str] = None
    NADRA_API_KEY: Optional[str] = None
    NADRA_CHANNEL_ID: Optional[str] = None
    NADRA_TIMEOUT_SECONDS: float = 8.0

    # Business rules
    COMPANY_LEGAL_NAME: str = "SahulatKar (Pvt) Ltd."
    MURABAHA_VALIDITY_DAYS: int = 3
    WAKALAH_VALIDITY_HOURS: int = 24
    MAX_ACTIVE_ORDERS_PER_USER: int = 5
    PROFIT_RATES: Dict[str, float] = {"3": 2.5, "4": 4.0, "6": 7.0, "12": 15.0}

    # HIGH-4: cross-service HTTP calls (InternalServiceClient) — retry-with-backoff
    # tuning. A flat 10s-timeout-no-retry call to a briefly-restarting neighbor
    # service (product-service, notification-service) previously failed outright
    # on the first blip.
    INTERNAL_HTTP_TIMEOUT_SECONDS: float = 10.0
    INTERNAL_HTTP_MAX_RETRIES: int = 3
    INTERNAL_HTTP_RETRY_BACKOFF_BASE_SECONDS: float = 0.5

    # HIGH-4: proactive sweep for orders stuck in an intermediate state (e.g.
    # "url_received" past the extraction timeout) — previously only healed when
    # a user happened to poll GET /orders/{id}/offer.
    ORDER_STUCK_SWEEP_INTERVAL_SECONDS: int = 120
    ORDER_STUCK_EXTRACTION_TIMEOUT_SECONDS: int = 600

    # HIGH-3: HITL sla_deadline escalation sweep interval, and how often the
    # same still-breached item is re-alerted (avoids re-logging a CRITICAL
    # every sweep cycle for an item nobody has actioned yet).
    HITL_SLA_SWEEP_INTERVAL_SECONDS: int = 300
    HITL_SLA_ALERT_DEDUP_SECONDS: int = 3600

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# AWS Secrets Manager migration (docs/SECRETS_MANAGER_MIGRATION.md): the subset
# of the fields above that are genuine credentials/connection secrets (not
# business config like PROFIT_RATES or MURABAHA_VALIDITY_DAYS). Keys are the
# dash-case Secrets Manager suffix under "gateway/<environment>/", values are
# the exact Settings field name above.
_SECRETS_MANAGER_FIELD_MAP = {
    "database-url": "DATABASE_URL",
    "redis-url": "REDIS_URL",
    "jwt-private-key": "JWT_PRIVATE_KEY",
    "jwt-public-key": "JWT_PUBLIC_KEY",
    "s3-access-key": "S3_ACCESS_KEY",
    "s3-secret-key": "S3_SECRET_KEY",
    "jazzcash-webhook-secret": "JAZZCASH_WEBHOOK_SECRET",
    "safepay-webhook-secret": "SAFEPAY_WEBHOOK_SECRET",
    "stripe-webhook-secret": "STRIPE_WEBHOOK_SECRET",
    "internal-service-token": "INTERNAL_SERVICE_TOKEN",
    "internal-api-key": "INTERNAL_API_KEY",
    "nadra-api-key": "NADRA_API_KEY",
}


def get_settings() -> Settings:
    """Get settings, trying AWS Secrets Manager first, then env vars/.env.

    Behavior (see docs/SECRETS_MANAGER_MIGRATION.md):
    1. If AWS_REGION is set, try loading the credential fields in
       _SECRETS_MANAGER_FIELD_MAP from AWS Secrets Manager
       ("gateway/<ENVIRONMENT>/<key>").
    2. On any failure (missing secret, AWS API error), log a warning and
       fall through to plain env vars / .env file -- identical to today's
       behavior.
    3. If AWS_REGION is unset (every local/test run), this never even
       imports boto3: zero behavior change for local development.
    """
    if os.getenv("AWS_REGION"):
        try:
            overrides = load_secrets_manager_overrides(
                service_prefix="gateway",
                environment=os.getenv("ENVIRONMENT", "prod"),
                secret_field_map=_SECRETS_MANAGER_FIELD_MAP,
                region=os.getenv("AWS_REGION"),
            )
            return Settings(**overrides)
        except SecretsManagerLoadError as exc:
            logger.warning(
                "Failed to load settings from AWS Secrets Manager, falling back to env vars/.env: %s",
                exc,
            )

    return Settings()


settings = get_settings()


def validate_critical_settings() -> None:
    """Abort startup if critical config is still at an insecure/placeholder default.

    Delegates to sk_shared.boot_validation (shared by product-service and
    notification-service) instead of reimplementing the "still a placeholder
    outside local" rule here. This is a deliberate widening from the previous
    gateway-only "production" scope to "any non-local environment" — matching
    every other service's convention — since gateway holds JWT signing keys,
    DB creds, and INTERNAL_API_KEY, and staging/test deployments deserve the
    same guard as production.
    """
    raise_if_placeholder_credentials(
        [
            ("KMS_MOCK_KEY_HEX", settings.KMS_MOCK_KEY_HEX, "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"),
            ("INTERNAL_SERVICE_TOKEN", settings.INTERNAL_SERVICE_TOKEN, "local-internal-token"),
            ("INTERNAL_API_KEY", settings.INTERNAL_API_KEY, "test-key"),
            # Required-but-missing secrets: normalize None -> "" so they are
            # expressed as "placeholder value is empty", matching the old
            # `if not settings.X` checks for both unset (None) and blank ("").
            ("STRIPE_WEBHOOK_SECRET", settings.STRIPE_WEBHOOK_SECRET or "", ""),
            ("S3_BUCKET", settings.S3_BUCKET or "", ""),
            ("SECP_LICENSE_NUMBER", settings.SECP_LICENSE_NUMBER or "", ""),
            ("JWT_PRIVATE_KEY", settings.JWT_PRIVATE_KEY or "", ""),
        ],
        environment=settings.ENVIRONMENT,
        error_prefix="PRODUCTION_CONFIG_VALIDATION_FAILED",
    )

    # Only required once NADRA_PROVIDER is switched to "verisys" — the
    # default "mock" provider needs no external credentials, so it must not
    # block staging/prod deploys that haven't completed NADRA onboarding yet.
    if settings.NADRA_PROVIDER == "verisys":
        raise_if_placeholder_credentials(
            [
                ("NADRA_API_URL", settings.NADRA_API_URL or "", ""),
                ("NADRA_API_KEY", settings.NADRA_API_KEY or "", ""),
            ],
            environment=settings.ENVIRONMENT,
            error_prefix="PRODUCTION_CONFIG_VALIDATION_FAILED",
        )
