from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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


settings = Settings()