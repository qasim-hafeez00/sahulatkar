from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


from decimal import Decimal

class VcnIssueRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    amount_pkr: Decimal = Field(..., gt=0, decimal_places=2)
    merchant_domain: Optional[str] = None


class VcnIssueResponse(BaseModel):
    vcn_id: int
    order_id: int
    status: str
    pan: str                  # Masked: **** **** **** XXXX
    expiry_month: str
    expiry_year: str
    cvv: str                  # Always "***" in this response
    issued_at: datetime
    expires_at: datetime


class VcnDecryptResponse(BaseModel):
    """
    Only returned to authenticated internal callers (X-Internal-Token).
    Used by the Product Service checkout agent to load the VCN into the browser.
    Never exposed to external/user-facing endpoints.
    """
    vcn_id: int
    order_id: int
    pan: str                  # Full 16-digit PAN
    expiry_month: str
    expiry_year: str
    cvv: str                  # 3-digit CVV
    cardholder_name: str      # SahulatKar Agent
    expires_at: datetime


class VcnStatusResponse(BaseModel):
    status: str
    charged_amount: float
    is_used: bool
    issued_at: datetime
    expires_at: datetime