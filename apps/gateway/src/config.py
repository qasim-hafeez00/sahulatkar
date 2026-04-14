from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"
    
    # DB
    DATABASE_URL: str = "postgresql+asyncpg://sk_app:password@localhost:5432/sahulatkar"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT Config
    JWT_PRIVATE_KEY: str = ""
    JWT_PUBLIC_KEY: str = ""
    JWT_ACCESS_TTL: int = 900  # 15 minutes
    JWT_REFRESH_TTL: int = 86400  # 24 hours
    
    # OTP 
    OTP_TTL: int = 180  # 3 minutes
    MAX_OTP_ATTEMPTS: int = 3
    OTP_ATTEMPTS_TTL: int = 300  # 5 minutes
    # S3 Storage (Optional, fallback to LocalStorage if missing)
    S3_BUCKET: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None
    CONTRACT_STORAGE_DIR: str = "./tmp/contracts"

    # Notifications
    NOTIFICATION_SMS_ENABLED: bool = True
    
    # Admin
    ADMIN_SESSION_TTL: int = 28800  # 8 hours

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
