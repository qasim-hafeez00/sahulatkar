from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "ledger-service"
    database_url: str = "postgresql+asyncpg://sk_app:localdev123@localhost:5432/sahulatkar"
    redis_url: str = "redis://:localdev123@localhost:6379/4"
    redis_db: int = 4
    billing_sweep_cron: str = "0 8 * * *"
    reconciliation_cron: str = "0 2 * * *"
    tasdeeq_mode: str = "batch_csv"
    default_charity_registration_number: str = "CHARITY-EDHI-001"
    payment_service_url: str = "http://payment-orchestrator:8000"

    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")


settings = Settings()