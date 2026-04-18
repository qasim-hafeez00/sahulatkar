from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from sk_shared.models.kyc import KycStatus


class CustomerProfileBase(BaseModel):
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    cnic: str = Field(..., max_length=15, pattern=r"^\d{5}-\d{7}-\d$")
    dob: datetime
    address: Optional[str] = Field(None, max_length=255)


class CustomerProfileResponse(CustomerProfileBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KycStartRequest(BaseModel):
    pass


class KycUploadResponse(BaseModel):
    status: KycStatus
    missing_documents: list[str]


class KycVerificationResponse(BaseModel):
    id: int
    status: KycStatus
    cnic_front_image_url: Optional[str]
    cnic_back_image_url: Optional[str]
    liveness_video_url: Optional[str]
    rejection_reason: Optional[str]
    attempt_number: int = 1
    nadra_verified_at: Optional[datetime] = None
    rejection_code: Optional[str] = None

    class Config:
        from_attributes = True

class KycQueueItemResponse(BaseModel):
    id: int
    kyc_verification_id: int
    assigned_admin_id: Optional[int] = None
    claimed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminKycDecisionRequest(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None
