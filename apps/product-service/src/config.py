from typing import List, Literal, Optional
import logging
import os
from decimal import Decimal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sk_shared.boot_validation import check_placeholder_credentials, raise_if_placeholder_credentials
from sk_shared.secrets_manager import SecretsManagerLoadError, load_secrets_manager_overrides

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql+asyncpg://sk_app:password@localhost:5432/sahulatkar"
    # GAP-B FIX: explicit dialect flag avoids deprecated session.bind usage in SQLAlchemy 2.x.
    # Set to "sqlite" in test environments via conftest.py / environment variable.
    DATABASE_DIALECT: str = "postgresql"

    # P1-05: PricingService.is_shariah_approved used to be a hardcoded
    # `True` class attribute backed only by a code comment claiming
    # sign-off — unverifiable and untraceable to any actual approval record.
    # It is now derived from these two fields instead: empty by default (not
    # approved), and only reads as approved once a real Shariah-board
    # reference/date is configured — see PricingService.is_shariah_approved.
    SHARIAH_MARKUP_APPROVAL_REFERENCE: str = ""
    SHARIAH_MARKUP_APPROVAL_DATE: str = ""
    REDIS_URL: str = "redis://localhost:6379/1"
    REDIS_DB: int = 1

    # Free-tier posture: Rye ($0.02/fetch) and OpenAI Vision (paid self-heal
    # fallback) stay off by default; Groq (generous free tier) is the only
    # LLM used for Tier 3 extraction until a paid budget is approved. Violet
    # and CAPTCHA solving are effectively no-ops anyway without an API key
    # configured (see VIOLET_API_KEY / CAPTCHA_API_KEY below), so their flags
    # don't need to change — cost is gated by the key, not just the flag.
    FEATURE_RYE_ENABLED: bool = False
    FEATURE_VIOLET_ENABLED: bool = True
    FEATURE_GROQ_ENABLED: bool = True
    FEATURE_OPENAI_FALLBACK: bool = False
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
    # Coarser than PRICE_DRIFT_THRESHOLD_PCT (checkout-time re-verification): this
    # is a sanity cross-check between the LLM-based Tier 3 extractor's price and
    # an earlier tier's independent (even if below-confidence-threshold) price
    # candidate, to catch a manipulated/hallucinated LLM price before it becomes
    # the purchase cost basis. Tiers can legitimately disagree more than 5% due
    # to rounding/currency display, so this tolerance is intentionally wider.
    TIER3_PRICE_CROSSCHECK_TOLERANCE_PCT: Decimal = Field(default=Decimal("35.0"), ge=Decimal("0"), le=Decimal("500"))
    HITL_SLA_MINUTES: int = Field(default=15, ge=1, le=1440)
    MIN_PRODUCT_PRICE_PKR: Decimal = Field(default=Decimal("1"), ge=Decimal("0"))
    MAX_PRODUCT_PRICE_PKR: Decimal = Field(default=Decimal("200000"), ge=Decimal("1"))
    PRODUCT_CACHE_TTL_SECONDS: int = Field(default=3600, ge=60, le=604800)
    PRODUCT_STALE_AFTER_SECONDS: int = Field(default=86400, ge=3600, le=604800)
    PRODUCT_STALENESS_BATCH_SIZE: int = Field(default=50, ge=1, le=500)
    PRODUCT_STALENESS_CHECK_INTERVAL_SECONDS: int = Field(default=3600, ge=300, le=86400)
    VCN_VERIFICATION_TIMEOUT_SECONDS: int = Field(default=120, ge=10, le=600)
    IMAGE_CACHE_ENABLED: bool = True
    # GAP-C: /extract endpoint rate limit (requests per minute per user/IP).
    EXTRACT_RATE_LIMIT_PER_MINUTE: int = Field(default=10, ge=1, le=1000)

    # Shariah Compliance Hardening
    SHARIAH_DOMAIN_DENYLIST: List[str] = [
        "alcohol.pk", "bet365.com", "1xbet.com", "pornhub.com", 
        "casino.org", "pokerstars.com", "wine.com"
    ]
    SHARIAH_CATEGORY_MAPPING: dict = {
        "Electronics": ["phone", "laptop", "camera", "tv", "earbud", "mobile", "tech"],
        "Fashion": ["shirt", "dress", "shoes", "wear", "cloth", "fashion", "bag"],
        "Home & Living": ["furniture", "decor", "kitchen", "bed", "home", "living"],
        "Health & Beauty": ["makeup", "skincare", "perfume", "beauty", "health", "care"],
        "Baby & Toys": ["toy", "baby", "kid", "child", "game"],
        "Sports & Outdoor": ["sport", "gym", "outdoor", "fitness", "cycle"],
        "Automotive": ["car", "bike", "auto", "vehicle", "tool"],
        "Books & Stationery": ["book", "stationery", "pen", "office", "read"],
    }

    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_SCREENSHOTS: str = "sk-screenshots-dev"
    PRODUCT_IMAGE_BUCKET: str = "sk-product-images-dev"
    AWS_KMS_KEY_ARN: str = ""
    # Set to use an S3-compatible provider (e.g. Cloudflare R2) instead of
    # real AWS — see src/services/s3_service.py::S3Service._client_kwargs.
    # Leave all three unset to use real AWS via the default credential chain.
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    INTERNAL_SERVICE_TOKEN: str = "dev-secret-token"
    JWT_PUBLIC_KEY: str = ""

    # Payment Orchestrator internal API — used by the checkout agent to fetch
    # plaintext VCN PAN/CVV just-in-time instead of carrying card data through
    # Redis queues/DLQ (see PO's require_internal_token, header "X-Internal-Token").
    PAYMENT_ORCHESTRATOR_URL: str = "http://payment-orchestrator:8000"

    INTERNAL_HTTP_CONNECT_TIMEOUT_SECONDS: float = Field(default=5.0, ge=0.1, le=30.0)
    INTERNAL_HTTP_READ_TIMEOUT_SECONDS: float = Field(default=30.0, ge=1.0, le=300.0)

    @model_validator(mode="after")
    def _validate_runtime_constraints(self):
        if self.MIN_PRODUCT_PRICE_PKR > self.MAX_PRODUCT_PRICE_PKR:
            raise ValueError("MIN_PRODUCT_PRICE_PKR cannot be greater than MAX_PRODUCT_PRICE_PKR")
        # Fail fast at Settings construction if the internal service token is
        # still the local-only placeholder outside the local environment.
        # Delegates to the shared-kernel "still at placeholder" rule instead
        # of reimplementing the comparison here (see also
        # `validate_critical_settings()` below, which covers the broader set
        # of external-service credentials at application boot).
        errors = check_placeholder_credentials(
            [("INTERNAL_SERVICE_TOKEN", self.INTERNAL_SERVICE_TOKEN, "dev-secret-token")],
            environment=self.ENVIRONMENT,
        )
        if errors:
            raise ValueError(errors[0])
        return self

    @property
    def cors_allow_origins_list(self) -> List[str]:
        if self.ENVIRONMENT == "local":
            return ["*"]
        return ["https://api.sahulatkar.com", "https://gateway.sahulatkar.internal"]

    CORS_ALLOW_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# AWS Secrets Manager migration (docs/SECRETS_MANAGER_MIGRATION.md): credential
# fields only -- not feature flags, price thresholds, or the Shariah
# category/domain lists. Keys are the dash-case Secrets Manager suffix under
# "product-service/<environment>/", values are the exact Settings field name.
_SECRETS_MANAGER_FIELD_MAP = {
    "database-url": "DATABASE_URL",
    "redis-url": "REDIS_URL",
    "rye-api-key": "RYE_API_KEY",
    "violet-api-key": "VIOLET_API_KEY",
    "groq-api-key": "GROQ_API_KEY",
    "openai-api-key": "OPENAI_API_KEY",
    "brightdata-proxy-url": "BRIGHTDATA_PROXY_URL",
    "captcha-api-key": "CAPTCHA_API_KEY",
    "fernet-key": "FERNET_KEY",
    "internal-service-token": "INTERNAL_SERVICE_TOKEN",
    "jwt-public-key": "JWT_PUBLIC_KEY",
    "s3-access-key": "S3_ACCESS_KEY",
    "s3-secret-key": "S3_SECRET_KEY",
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
                service_prefix="product-service",
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
    """Abort startup outside `local` if required external credentials are
    still missing or at their insecure/dev-only placeholder defaults.

    product-service calls out to several metered, costed third-party APIs
    per extraction request (Rye API, BrightData proxy, Groq/GPT-4o Vision)
    and stores screenshots/product images in S3 -- booting without real
    credentials for these outside `local` means either silently degraded
    extraction tiers or requests failing well after boot instead of at
    startup, where it's easiest to catch. Delegates to the shared-kernel
    boot validator (`sk_shared.boot_validation`) instead of duplicating the
    "still equal to placeholder" comparison per setting.

    RYE_API_KEY is only checked when FEATURE_RYE_ENABLED is set -- the flag
    already defaults to False (Rye is an optional extraction tier gated by
    `not settings.FEATURE_RYE_ENABLED or not settings.RYE_API_KEY` in
    extraction_waterfall.py), so requiring the key unconditionally would
    make every non-local deployment that intentionally leaves Rye disabled
    fail to boot.
    """
    checks: list[tuple[str, object, object]] = [
        ("BRIGHTDATA_PROXY_URL", settings.BRIGHTDATA_PROXY_URL, ""),
        ("GROQ_API_KEY", settings.GROQ_API_KEY, ""),
        ("INTERNAL_SERVICE_TOKEN", settings.INTERNAL_SERVICE_TOKEN, "dev-secret-token"),
        ("S3_BUCKET_SCREENSHOTS", settings.S3_BUCKET_SCREENSHOTS, "sk-screenshots-dev"),
        ("PRODUCT_IMAGE_BUCKET", settings.PRODUCT_IMAGE_BUCKET, "sk-product-images-dev"),
    ]
    if settings.FEATURE_RYE_ENABLED:
        checks.append(("RYE_API_KEY", settings.RYE_API_KEY, ""))

    raise_if_placeholder_credentials(
        checks,
        environment=settings.ENVIRONMENT,
        settings_obj=settings,
        error_prefix="PRODUCT_SERVICE_CONFIG_VALIDATION_FAILED",
    )
