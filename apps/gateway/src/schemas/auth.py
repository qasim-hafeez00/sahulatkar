from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID

class RegisterInitiateRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+92[0-9]{10}$", description="E.164 formatted phone number")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = None
    referral_code: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)

class RegisterInitiateResponse(BaseModel):
    otp_token: str
    masked_phone: str
    dev_otp: Optional[str] = Field(default=None, description="[DEV ONLY] OTP code — not present in production")

class VerifyOtpRequest(BaseModel):
    otp_token: str
    otp_code: str = Field(..., min_length=6, max_length=6)

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: int
    kyc_status: str

class LoginRequest(BaseModel):
    phone: str
    otp_code: Optional[str] = None
    password: Optional[str] = None

class AdminLoginRequest(BaseModel):
    email: str
    password: str
    totp_code: Optional[str] = None  # Required only when admin.mfa_enabled is True

class AdminAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin_id: int
    role: str


class AdminMfaSetupResponse(BaseModel):
    qr_uri: str
    secret: str


class AdminMfaVerifyRequest(BaseModel):
    totp_code: str = Field(min_length=6, max_length=6)

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class TokenRefreshResponse(BaseModel):
    access_token: str

class ResendOtpRequest(BaseModel):
    otp_token: str

class CurrentUserResponse(BaseModel):
    user_id: int
    uuid: UUID
    phone: str
    kyc_status: str
    credit_limit: Optional[float]
    available_credit: float
    status: str

    model_config = ConfigDict(from_attributes=True)


class ForgotPasswordRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+92[0-9]{10}$", description="E.164 Pakistan phone number")


class ResetPasswordRequest(BaseModel):
    reset_token: str
    otp_code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)


class DeviceRegisterRequest(BaseModel):
    device_token: str = Field(..., min_length=10, max_length=512)
    platform: str = Field(..., pattern="^(ios|android)$")


class AccountDeleteRequest(BaseModel):
    password: str = Field(..., min_length=1)
