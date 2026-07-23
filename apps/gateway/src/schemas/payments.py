from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field


class DownPaymentRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    method: str = Field(..., pattern="^(safepay|jazzcash|easypaisa|raast)$")
    amount_pkr: Decimal = Field(..., gt=0)


class DownPaymentResponse(BaseModel):
    payment_id: int
    status: str
    checkout_url: Optional[str] = None
    transaction_id: Optional[str] = None


class InstallmentDetail(BaseModel):
    id: int
    number: int
    due_date: date
    amount: Decimal
    status: str
    paid_at: Optional[datetime] = None


class PaymentScheduleResponse(BaseModel):
    loan_id: int
    loan_number: str
    total_amount: Decimal
    installments: List[InstallmentDetail]


class VcnIssueRequest(BaseModel):
    order_id: int = Field(..., gt=0)


class VcnIssueResponse(BaseModel):
    status: str
    order_id: int


class PaymentMethodCreateRequest(BaseModel):
    provider: str = Field(..., pattern="^(jazzcash|easypaisa|safepay|raast|card)$")
    method_type: str = Field(..., pattern="^(wallet|card|bank)$")
    account_identifier: str = Field(..., min_length=4, max_length=34, description="Wallet mobile number, masked card PAN, or IBAN")
    expiry_month: Optional[str] = Field(default=None, pattern=r"^(0[1-9]|1[0-2])$")
    expiry_year: Optional[str] = Field(default=None, pattern=r"^\d{4}$")


class PaymentMethodResponse(BaseModel):
    id: int
    provider: str
    method_type: str
    masked_pan: Optional[str] = None
    expiry_month: Optional[str] = None
    expiry_year: Optional[str] = None
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True
