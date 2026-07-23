import logging
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

from sk_shared.boot_validation import raise_if_placeholder_credentials
from sk_shared.secrets_manager import SecretsManagerLoadError, load_secrets_manager_overrides

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    environment: str = "local"
    service_name: str = "ledger-service"
    database_url: str = "postgresql+asyncpg://sk_app:localdev123@localhost:5432/sahulatkar"
    redis_url: str = "redis://:localdev123@localhost:6379/4"
    redis_db: int = 4
    billing_sweep_cron: str = "0 8 * * *"
    reconciliation_cron: str = "0 2 * * *"
    tasdeeq_mode: str = "batch_csv"
    tasdeeq_endpoint_url: str = ""
    tasdeeq_api_token: str = ""
    tasdeeq_timeout_seconds: int = 15
    tasdeeq_max_retries: int = 3
    tasdeeq_audit_dir: str = "tmp/tasdeeq"
    reconciliation_audit_dir: str = "tmp/reconciliation"
    default_charity_registration_number: str = "CHARITY-EDHI-001"
    payment_service_url: str = "http://payment-orchestrator:8000"
    internal_api_token: str = "change-me"

    # LS-BL-04: Shariah wealth thresholds — configurable without code deploy.
    # nisab_pkr: Minimum wealth threshold in PKR below which zakat/charity is not due.
    # Defaults to approx 85g gold equivalent in PKR (PKR 175,000 as of 2024).
    shariah_nisab_pkr: float = 175_000.0
    # haul_months: Number of months wealth must be held before charity is obligatory.
    shariah_haul_months: int = 12
    # charity_disbursement_min_age_days: Minimum age (days) of an allocation before auto-disbursement.
    charity_disbursement_min_age_days: int = 7

    # LS-CRIT-05: DLQ consumer settings
    dlq_max_retries: int = 3
    dlq_retry_base_delay_seconds: float = 2.0
    dlq_poll_interval_seconds: float = 30.0
    dlq_alert_threshold: int = 100  # Alert if DLQ depth exceeds this

    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")


# AWS Secrets Manager migration (docs/SECRETS_MANAGER_MIGRATION.md): this is
# the service the doc's own example was written against (its example used
# the "ledger" shorthand and a slightly different field list than what's
# actually in this class today -- e.g. redis_db/tasdeeq_mode/billing_sweep_cron
# are operational config, not secrets, so they're intentionally left out
# here). Namespaced under "ledger-service" (matching this app's directory
# name and its "sk-ledger-service" K8s ServiceAccount) rather than the doc's
# "ledger" shorthand, for consistency with the other 4 services' prefixes.
# Keys are the dash-case Secrets Manager suffix under
# "ledger-service/<environment>/", values are the exact Settings field name.
_SECRETS_MANAGER_FIELD_MAP = {
    "database-url": "database_url",
    "redis-url": "redis_url",
    "tasdeeq-api-token": "tasdeeq_api_token",
    "internal-api-token": "internal_api_token",
    "payment-service-url": "payment_service_url",
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
                service_prefix="ledger-service",
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
    """Abort startup outside `local` if required credentials are still at
    their insecure placeholder defaults.

    ledger-service authenticates internal callers (e.g. other services
    invoking its admin/internal endpoints) using `internal_api_token`
    (see `src.core.dependencies.require_internal_request`). Booting outside
    `local` with the "change-me" placeholder would silently accept any
    caller presenting the well-known default token. Delegates to the
    shared-kernel boot validator (`sk_shared.boot_validation`) instead of
    duplicating the "still equal to placeholder" comparison here.
    """
    raise_if_placeholder_credentials(
        [("internal_api_token", settings.internal_api_token, "change-me")],
        environment=settings.environment,
        settings_obj=settings,
        error_prefix="LEDGER_SERVICE_CONFIG_VALIDATION_FAILED",
    )