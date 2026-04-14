from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    service_name: str = "credit-engine"
    database_url: str = "postgresql+asyncpg://sk_app:localdev123@localhost:6432/sahulatkar"
    redis_url: str = "redis://:localdev123@localhost:6379/2"

    # Credit Policy Parameters (defaults from M04 spec)
    auto_approve_threshold: int = 700
    manual_review_threshold: int = 600
    auto_decline_below: int = 600

    first_time_user_limit: float = 25000.0
    maximum_limit: float = 500000.0
    
    credit_increase_after_n_payments: int = 3
    credit_increase_pct: float = 0.25
    
    max_debt_to_income_ratio: float = 0.40
    min_monthly_income: float = 30000.0
    
    # Cold start caps
    cold_start_max_band_a: float = 8000.0
    cold_start_max_band_b: float = 5000.0
    cold_start_max_band_c: float = 3000.0
    cold_start_max_band_d: float = 2000.0
    
    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")

settings = Settings()
