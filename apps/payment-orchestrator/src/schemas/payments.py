from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PaymentMethodType(str, Enum):
    safepay = "safepay"
    jazzcash = "jazzcash"


class DownPaymentRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    method: PaymentMethodType
    amount_pkr: Decimal = Field(..., gt=0)


class DownPaymentResponse(BaseModel):
    status: str
    order_id: int
    payment_transaction_id: int
    payment_session_url: Optional[str] = None
    gateway_txn_id: Optional[str] = None


class PayInstallmentRequest(BaseModel):
    installment_id: int = Field(..., gt=0)
    method: PaymentMethodType
    payment_method_id: Optional[int] = None


class PayInstallmentResponse(BaseModel):
    success: bool
    txn_id: int
    paid_at: str
    next_installment_id: Optional[int] = None


class WebhookAck(BaseModel):
    status: str