from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VcnIssueRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    amount_pkr: float = Field(..., gt=0)
    merchant_domain: Optional[str] = None


class VcnIssueResponse(BaseModel):
    vcn_id: int
    order_id: int
    status: str
    pan: str
    expiry_month: str
    expiry_year: str
    cvv: str
    issued_at: datetime
    expires_at: datetime


class VcnStatusResponse(BaseModel):
    status: str
    charged_amount: float
    is_used: bool
    issued_at: datetime
    expires_at: datetime