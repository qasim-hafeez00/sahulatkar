from decimal import Decimal
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


class MandateSetupRequest(BaseModel):
    gateway: str = Field(..., description="E.g., raast, jazzcash")
    payer_identifier: str = Field(..., description="IBAN or phone number")
    max_amount_per_txn: Optional[Decimal] = Field(None, gt=0)


class MandateSetupResponse(BaseModel):
    mandate_id: int
    status: str
    mandate_reference: str
    payer_identifier: str
    authorization_url: Optional[str] = None
    message: str


class MandateStatusResponse(BaseModel):
    mandate_reference: str
    gateway: str
    status: str
    payer_identifier: str
    max_amount_per_txn: Optional[Decimal]
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
