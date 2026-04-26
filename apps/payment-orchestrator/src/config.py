from decimal import Decimal
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Runtime ─────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "payment-orchestrator"

    # ── Database / Redis ─────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://sk_app:password@localhost:5432/sahulatkar"
    REDIS_URL: str = "redis://localhost:6379/3"
    REDIS_DB: int = 3

    # ── JWT (public key from Gateway, used to verify user tokens) ────────────
    JWT_PUBLIC_KEY: str = ""
    JWT_PRIVATE_KEY: str = ""

    # ── Internal Service Auth (shared KMS secret, constant-time compared) ────
    INTERNAL_API_TOKEN: str = ""

    # ── Stripe Issuing ────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_POLLING_MAX_RETRIES: int = 5
    STRIPE_POLLING_INTERVAL_SECONDS: int = 3

    # ── SafePay ───────────────────────────────────────────────────────────────
    SAFEPAY_API_KEY: str = ""
    SAFEPAY_API_SECRET: str = ""
    SAFEPAY_BASE_URL: str = "https://sandbox.safepay.pk"

    # ── JazzCash ──────────────────────────────────────────────────────────────
    JAZZCASH_MERCHANT_ID: str = ""
    JAZZCASH_PASSWORD: str = ""
    JAZZCASH_BASE_URL: str = "https://sandbox.jazzcash.com.pk"

    # ── EasyPaisa ─────────────────────────────────────────────────────────────
    EASYPAISA_STORE_ID: str = ""
    EASYPAISA_HASH_KEY: str = ""
    EASYPAISA_BASE_URL: str = "https://easypaystg.easypaisa.com.pk"

    # ── Raast (SBP — Primary Gateway) ─────────────────────────────────────────
    # Raast IBFT is provided through a licensed payment gateway aggregator
    # (e.g. 1LINK / NayaPay / affiliated bank). Endpoint and credentials are
    # issued by the acquiring bank. Replace base_url for production.
    RAAST_API_KEY: str = ""
    RAAST_API_SECRET: str = ""
    RAAST_BASE_URL: str = "https://sandbox.raast-gateway.pk/api/v1"
    RAAST_MERCHANT_IBAN: str = ""          # SahulatKar's receiving IBAN
    RAAST_WEBHOOK_SECRET: str = ""

    # ── VCN Config ────────────────────────────────────────────────────────────
    VCN_ENCRYPTION_KEY: str = ""           # Fernet key dedicated to VCN PAN/CVV encryption
    VCN_EXPIRY_HOURS: int = 24
    VCN_BUFFER_PCT: float = 5.0            # Authorized 5% above product price as buffer

    # ── Payment Config ────────────────────────────────────────────────────────
    PAYMENT_CURRENCY: str = "PKR"
    DOWN_PAYMENT_MIN_PCT: Decimal = Decimal("25.0")
    DOWN_PAYMENT_MAX_PCT: Decimal = Decimal("40.0")

    # ── Routing Engine ────────────────────────────────────────────────────────
    # Redis key TTL for gateway failure counters (seconds)
    GATEWAY_FAILURE_WINDOW_SECONDS: int = 300
    # Number of failures within window before a gateway is deprioritised
    GATEWAY_FAILURE_THRESHOLD: int = 5

    # ── Worker / DLQ Config ───────────────────────────────────────────────────
    VCN_WORKER_CONCURRENCY: int = 4
    DLQ_MAX_RETRIES: int = 3               # Attempts before pushing to DLQ

    # ── Reconciliation ────────────────────────────────────────────────────────
    RECONCILIATION_AUDIT_DIR: str = "/tmp/recon-audit"

    # ── Retry / Resilience ───────────────────────────────────────────────────
    MAX_INSTALLMENT_RETRIES: int = 3                     # Used in billing sweep trigger
    INSTALLMENT_RETRY_DELAY_HOURS: List[int] = Field(default_factory=lambda: [0, 24, 48])

    # ── Session / Workflow ────────────────────────────────────────────────────
    PAYMENT_SESSION_TTL_MINUTES: int = 30               # PaymentWorkflow session expiry

    # ── VCN Expiry Worker ─────────────────────────────────────────────────────
    VCN_EXPIRY_SWEEP_INTERVAL_SECONDS: int = 300        # How often VcnExpiryWorker runs
    VCN_STATUS_POLL_INTERVAL_SECONDS: int = 600         # GAP-05: How often StripePollerWorker runs

    # ── FX / Currency ─────────────────────────────────────────────────────────
    FX_PKR_TO_USD_RATE: float = 0.0036                  # Required for Stripe Issuing USD conversion
    FX_BUFFER_PCT: float = 2.0                          # FX drift tolerance buffer (%)

    # ── Outbox Publisher ──────────────────────────────────────────────────────
    OUTBOX_POLL_INTERVAL_SECONDS: int = 5               # OutboxPublisher loop interval
    OUTBOX_BATCH_SIZE: int = 50                         # Events per poll cycle

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ALLOW_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "https://app.sahulatkar.pk",
            "https://admin.sahulatkar.pk",
        ]
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()