from typing import List, Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────────
    SERVICE_NAME: str = "notification-service"
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


settings = Settings()
