import logging
import os
from typing import List, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sk_shared.secrets_manager import SecretsManagerLoadError, load_secrets_manager_overrides

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────────
    SERVICE_NAME: str = "notification-service"
    ENVIRONMENT: str = "local"
    DATABASE_URL: str = "postgresql+asyncpg://sk_app:password@localhost:5432/sahulatkar"
    REDIS_URL: str = "redis://localhost:6379/5"
    REDIS_DB: int = 5
    LOG_LEVEL: str = "INFO"
    CORS_ALLOW_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])
    CUSTOMER_WEB_URL: str = "https://app.sahulatkar.pk"

    # ── AfterShip ─────────────────────────────────────────────────────────────
    AFTERSHIP_API_KEY: str = ""
    AFTERSHIP_WEBHOOK_SECRET: str = ""
    AFTERSHIP_BASE_URL: str = "https://api.aftership.com/v4"

    # ── Internal Auth ─────────────────────────────────────────────────────────
    # Shared secret with the Gateway: verifies X-Internal-Key on machine-to-machine
    # calls (require_internal_key) AND signs/verifies the short-lived X-Admin-Assertion
    # the Gateway mints to propagate an authenticated admin's role/permissions
    # (see sk_shared.security.create_signed_assertion / verify_signed_assertion).
    INTERNAL_API_KEY: str = "test-key"

    # ── SMS — Jazz / Rozan ────────────────────────────────────────────────────
    # Jazz SMS API (primary). Fallback: Twilio.
    JAZZ_SMS_API_URL: str = "https://sms.jazz.com.pk/api/send"
    JAZZ_SMS_USERNAME: str = ""
    JAZZ_SMS_PASSWORD: str = ""
    JAZZ_SMS_SENDER_ID: str = "SahulatKar"

    SMS_FALLBACK_PROVIDER: Literal["twilio", "none"] = "twilio"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_SMS_FROM: str = "+1234567890"

    # ── WhatsApp — Jazz Business API ──────────────────────────────────────────
    JAZZ_WHATSAPP_API_URL: str = "https://waba.jazz.com.pk/v1/messages"
    JAZZ_WHATSAPP_API_KEY: str = ""
    JAZZ_WHATSAPP_FROM_NUMBER: str = ""
    # Fallback: Twilio WhatsApp
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+1234567890"
    WHATSAPP_FALLBACK_PROVIDER: Literal["twilio", "none"] = "twilio"

    # ── Push — Firebase FCM v1 ────────────────────────────────────────────────
    FCM_PROJECT_ID: str = ""
    FCM_SERVICE_ACCOUNT_JSON: str = ""  # base64-encoded service account JSON
    FCM_API_URL: str = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

    # ── Email — SendGrid ──────────────────────────────────────────────────────
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "noreply@sahulatkar.pk"
    SENDGRID_FROM_NAME: str = "SahulatKar"
    SENDGRID_WEBHOOK_SECRET: str = ""  # for delivery receipt webhooks
    JAZZ_SMS_WEBHOOK_SECRET: str = ""
    JAZZ_WHATSAPP_WEBHOOK_SECRET: str = ""

    # ── Dispatcher Behavior ───────────────────────────────────────────────────
    # Max retries per channel before moving to DLQ
    MAX_DISPATCH_RETRIES: int = 3
    RETRY_BACKOFF_BASE_SECONDS: int = 30  # exponential: 30s, 90s, 270s
    DLQ_ALERT_THRESHOLD: int = 50         # alert if DLQ depth exceeds this

    # Rate limits (per user, per channel, per window in minutes)
    SMS_RATE_LIMIT_PER_USER_PER_HOUR: int = 10
    WHATSAPP_RATE_LIMIT_PER_USER_PER_HOUR: int = 20
    PUSH_RATE_LIMIT_PER_USER_PER_HOUR: int = 50
    EMAIL_RATE_LIMIT_PER_USER_PER_DAY: int = 5

    # OTP SMS rate limit is separate and stricter
    OTP_SMS_RATE_LIMIT_PER_PHONE_PER_HOUR: int = 5
    OTP_SMS_RATE_LIMIT_PER_PHONE_PER_DAY: int = 20

    # ── Worker ────────────────────────────────────────────────────────────────
    NOTIFICATION_WORKER_CONCURRENCY: int = 10
    NOTIFICATION_QUEUE_KEY: str = "sk:queue:notifications"
    NOTIFICATION_RETRY_QUEUE_KEY: str = "sk:queue:notifications:retry"
    NOTIFICATION_DLQ_KEY: str = "sk:queue:notifications:dlq"

    # ── Scheduler ─────────────────────────────────────────────────────────────
    # Cron expression for the installment reminder scheduler
    REMINDER_SCHEDULER_CRON: str = "0 9 * * *"   # 9 AM PKT daily
    RETRY_WORKER_CRON: str = "*/5 * * * *"         # every 5 minutes

    # Reminder windows in days-before-due
    REMINDER_DAYS_BEFORE: List[int] = Field(default_factory=lambda: [3, 1])

    # ── Charity / Compliance ──────────────────────────────────────────────────
    CHARITY_ORGANIZATION_NAME: str = "Edhi Foundation"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _validate_runtime_constraints(self):
        if self.ENVIRONMENT != "local" and self.INTERNAL_API_KEY == "test-key":
            raise ValueError(
                "INTERNAL_API_KEY must be changed outside local environment — "
                "it is used both for X-Internal-Key auth and for signing/verifying "
                "the admin assertion trusted by admin_notifications/admin_tracking."
            )
        return self

    @property
    def cors_allow_origins_list(self) -> List[str]:
        """Gate wildcard CORS to local development only (mirrors product-service)."""
        if self.ENVIRONMENT == "local":
            return ["*"]
        return [self.CUSTOMER_WEB_URL, "https://admin.sahulatkar.pk"]


# AWS Secrets Manager migration (docs/SECRETS_MANAGER_MIGRATION.md): credential
# fields only -- not rate limits, retry backoff, or the reminder-window list.
# Keys are the dash-case Secrets Manager suffix under
# "notification-service/<environment>/", values are the exact Settings field name.
_SECRETS_MANAGER_FIELD_MAP = {
    "database-url": "DATABASE_URL",
    "redis-url": "REDIS_URL",
    "internal-api-key": "INTERNAL_API_KEY",
    "aftership-api-key": "AFTERSHIP_API_KEY",
    "aftership-webhook-secret": "AFTERSHIP_WEBHOOK_SECRET",
    "jazz-sms-username": "JAZZ_SMS_USERNAME",
    "jazz-sms-password": "JAZZ_SMS_PASSWORD",
    "twilio-account-sid": "TWILIO_ACCOUNT_SID",
    "twilio-auth-token": "TWILIO_AUTH_TOKEN",
    "jazz-whatsapp-api-key": "JAZZ_WHATSAPP_API_KEY",
    "fcm-service-account-json": "FCM_SERVICE_ACCOUNT_JSON",
    "sendgrid-api-key": "SENDGRID_API_KEY",
    "sendgrid-webhook-secret": "SENDGRID_WEBHOOK_SECRET",
    "jazz-sms-webhook-secret": "JAZZ_SMS_WEBHOOK_SECRET",
    "jazz-whatsapp-webhook-secret": "JAZZ_WHATSAPP_WEBHOOK_SECRET",
}


def get_settings() -> Settings:
    """Get settings, trying AWS Secrets Manager first, then env vars/.env.

    Same fallback contract as every other service (see
    docs/SECRETS_MANAGER_MIGRATION.md and gateway's src/config.py): only
    attempts Secrets Manager when AWS_REGION is set, and falls back to plain
    env vars/.env on any failure so local/test runs (no AWS_REGION) are
    unaffected. notification-service has no standalone
    validate_critical_settings() (its placeholder check lives directly in
    the @model_validator above); that validator still runs unchanged for
    both the Secrets-Manager-populated and the plain-env-var path, since both
    go through Settings.__init__.
    """
    if os.getenv("AWS_REGION"):
        try:
            overrides = load_secrets_manager_overrides(
                service_prefix="notification-service",
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
