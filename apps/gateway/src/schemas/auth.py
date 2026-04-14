from pydantic import BaseModel, ConfigDict, Field, constr
from typing import Optional
from uuid import UUID

class RegisterInitiateRequest(BaseModel):
    phone: str = Field(..., description="E.164 formatted phone number")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = None
    referral_code: Optional[str] = None

class RegisterInitiateResponse(BaseModel):
    otp_token: str
    masked_phone: str

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
    totp_code: str

class AdminAuthResponse(BaseModel):
    access_token: str
    admin_id: int
    role: str

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
