import logging
import os
from decimal import Decimal
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sk_shared.secrets_manager import SecretsManagerLoadError, load_secrets_manager_overrides

logger = logging.getLogger(__name__)


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

    # Self-referencing base URL — used by the event listener to call this
    # same service's own internal auto-collect endpoint (see
    # handle_payment_collection_triggered in events/listeners.py) rather than
    # duplicating that endpoint's business logic in the listener.
    SELF_BASE_URL: str = "http://localhost:8003"

    # Gateway's base URL — used by OutboxPublisher to notify Gateway when a
    # down payment is confirmed (event_name="gateway.payment_confirmed"), so
    # Gateway's own Order.status transition and saga-compensation logic in
    # POST /internal/payments/{payment_id}/confirm actually runs. Shares
    # INTERNAL_API_TOKEN as the auth secret (same shared internal token,
    # named INTERNAL_SERVICE_TOKEN on Gateway's side).
    GATEWAY_URL: str = "http://localhost:8000"

    # Public internet-facing URL for Gateway, used ONLY as the callback_url
    # handed to JazzCash/SafePay/Raast so they can reach Gateway's webhook
    # ingress from outside the cluster (see
    # src/workers/payment_initiate_consumer.py). Never use this for
    # service-to-service calls — use GATEWAY_URL (cluster-internal) instead.
    GATEWAY_PUBLIC_URL: str = "http://localhost:8000"

    # ── Stripe Issuing ────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_POLLING_MAX_RETRIES: int = 5
    STRIPE_POLLING_INTERVAL_SECONDS: int = 3

    # ── Lithic Issuing (second VCN issuer) ───────────────────────────────────
    # Off by default: Stripe Issuing remains the functional-today path. Lithic
    # requires a business/KYB approval process before it can issue a single
    # real card — this adapter is code-complete and testable against Lithic's
    # sandbox, but flipping this flag in production is gated on that approval
    # landing, not on this code. See docs for the full VCN cost/strategy note.
    FEATURE_LITHIC_ENABLED: bool = False
    LITHIC_API_KEY: str = ""
    LITHIC_BASE_URL: str = "https://sandbox.lithic.com/v1"
    LITHIC_CARD_PROGRAM_TOKEN: str = ""
    LITHIC_WEBHOOK_SECRET: str = ""

    # ── SafePay ───────────────────────────────────────────────────────────────
    SAFEPAY_API_KEY: str = ""
    SAFEPAY_API_SECRET: str = ""
    SAFEPAY_WEBHOOK_SECRET: str = ""
    # Live-verified against the real SafePay sandbox and the official PHP SDK
    # (getsafepay/safepay-php Base.php) — "sandbox.safepay.pk" doesn't exist
    # (NXDOMAIN); the real API lives on the getsafepay.com domain.
    SAFEPAY_BASE_URL: str = "https://sandbox.api.getsafepay.com"

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
    # Versioned-key envelope encryption for VCN PAN/CVV (see
    # src/services/vcn_encryption.py::VcnKeyProvider). VCN_ENCRYPTION_KEY is
    # the legacy/"v1" secret — kept under its original name for backward
    # compatibility with rows encrypted before key versioning existed.
    # Additional rotations are added by setting VCN_ENCRYPTION_KEY_V2,
    # VCN_ENCRYPTION_KEY_V3, ... and then bumping
    # VCN_ENCRYPTION_KEY_CURRENT_VERSION so *new* encryptions use the new
    # secret; old rows keep decrypting under whichever version is stamped on
    # them (VirtualCard.encryption_key_version) — no immediate re-encryption
    # required (see scripts/rotate_vcn_encryption_keys.py for offline
    # batch rotation of old rows onto the current version).
    VCN_ENCRYPTION_KEY: str = ""           # legacy/v1 Fernet key material for VCN PAN/CVV encryption
    VCN_ENCRYPTION_KEY_V2: str = ""
    VCN_ENCRYPTION_KEY_V3: str = ""
    VCN_ENCRYPTION_KEY_CURRENT_VERSION: str = "v1"
    VCN_EXPIRY_HOURS: int = 24
    VCN_BUFFER_PCT: float = 5.0            # Authorized 5% above product price as buffer

    # ── KMS (production envelope-encryption path for VCN keys) ───────────────
    # Local/test path (ENVIRONMENT != "production", or KMS_KEY_ARN unset):
    # VcnKeyProvider derives keys locally from VCN_ENCRYPTION_KEY* via
    # SHA-256, same as always. Production path: set ENVIRONMENT=production
    # and KMS_KEY_ARN to route new VCN encryptions through AWS KMS envelope
    # encryption instead. NOT YET IMPLEMENTED — see the TODO block in
    # VcnKeyProvider._kms_get_cipher (src/services/vcn_encryption.py) for the
    # intended design; leave KMS_KEY_ARN unset until that lands.
    KMS_KEY_ARN: Optional[str] = None

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
    PAYMENT_WEBHOOK_WORKER_CONCURRENCY: int = 4
    PAYMENT_INITIATE_WORKER_CONCURRENCY: int = 4
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


# AWS Secrets Manager migration (docs/SECRETS_MANAGER_MIGRATION.md):
# payment-orchestrator holds a live credential per payment gateway plus the
# VCN PAN/CVV encryption key material -- this is the widest credential list
# of the five services, matching validate_critical_settings() below plus the
# per-gateway secrets it doesn't (yet) enforce at boot (EasyPaisa). Keys are
# the dash-case Secrets Manager suffix under
# "payment-orchestrator/<environment>/", values are the exact Settings field name.
_SECRETS_MANAGER_FIELD_MAP = {
    "database-url": "DATABASE_URL",
    "redis-url": "REDIS_URL",
    "jwt-public-key": "JWT_PUBLIC_KEY",
    "internal-api-token": "INTERNAL_API_TOKEN",
    "stripe-secret-key": "STRIPE_SECRET_KEY",
    "stripe-webhook-secret": "STRIPE_WEBHOOK_SECRET",
    "lithic-api-key": "LITHIC_API_KEY",
    "lithic-webhook-secret": "LITHIC_WEBHOOK_SECRET",
    "safepay-api-key": "SAFEPAY_API_KEY",
    "safepay-api-secret": "SAFEPAY_API_SECRET",
    "safepay-webhook-secret": "SAFEPAY_WEBHOOK_SECRET",
    "jazzcash-merchant-id": "JAZZCASH_MERCHANT_ID",
    "jazzcash-password": "JAZZCASH_PASSWORD",
    "easypaisa-store-id": "EASYPAISA_STORE_ID",
    "easypaisa-hash-key": "EASYPAISA_HASH_KEY",
    "raast-api-key": "RAAST_API_KEY",
    "raast-api-secret": "RAAST_API_SECRET",
    "raast-merchant-iban": "RAAST_MERCHANT_IBAN",
    "raast-webhook-secret": "RAAST_WEBHOOK_SECRET",
    "vcn-encryption-key": "VCN_ENCRYPTION_KEY",
}


def get_settings() -> Settings:
    """Get settings, trying AWS Secrets Manager first, then env vars/.env.

    Same fallback contract as every other service (see
    docs/SECRETS_MANAGER_MIGRATION.md and gateway's src/config.py): only
    attempts Secrets Manager when AWS_REGION is set, and falls back to plain
    env vars/.env on any failure so local/test runs (no AWS_REGION) are
    unaffected.
    """
    if os.getenv("AWS_REGION"):
        try:
            overrides = load_secrets_manager_overrides(
                service_prefix="payment-orchestrator",
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
    """Abort startup if a live payment credential is still at its empty
    placeholder default outside the `local` environment.

    payment-orchestrator holds real secrets for every payment gateway
    (Stripe, Safepay, JazzCash, Raast) plus the VCN PAN/CVV encryption key —
    booting with any of these still unset would either silently fail every
    payment through that gateway, or (for VCN_ENCRYPTION_KEY) leave stored
    card PAN/CVV encrypted under an empty-string-derived key instead of a
    real secret. Delegates to sk_shared.boot_validation, which every service
    in the fleet is standardizing on for this "still a placeholder outside
    local" check (see packages/shared-python/sk_shared/boot_validation.py).
    """
    from sk_shared.boot_validation import raise_if_placeholder_credentials

    raise_if_placeholder_credentials(
        [
            ("STRIPE_SECRET_KEY", settings.STRIPE_SECRET_KEY, ""),
            ("SAFEPAY_API_KEY", settings.SAFEPAY_API_KEY, ""),
            ("SAFEPAY_API_SECRET", settings.SAFEPAY_API_SECRET, ""),
            ("JAZZCASH_MERCHANT_ID", settings.JAZZCASH_MERCHANT_ID, ""),
            ("JAZZCASH_PASSWORD", settings.JAZZCASH_PASSWORD, ""),
            ("RAAST_API_KEY", settings.RAAST_API_KEY, ""),
            ("RAAST_API_SECRET", settings.RAAST_API_SECRET, ""),
            ("RAAST_MERCHANT_IBAN", settings.RAAST_MERCHANT_IBAN, ""),
            ("VCN_ENCRYPTION_KEY", settings.VCN_ENCRYPTION_KEY, ""),
            ("INTERNAL_API_TOKEN", settings.INTERNAL_API_TOKEN, ""),
        ],
        environment=settings.ENVIRONMENT,
        settings_obj=settings,
        error_prefix="PAYMENT_ORCHESTRATOR_CONFIG_VALIDATION_FAILED",
    )