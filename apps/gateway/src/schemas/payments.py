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
