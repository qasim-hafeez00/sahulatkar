from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PaymentMethodType(str, Enum):
    safepay = "safepay"
    jazzcash = "jazzcash"
    raast = "raast"


class DownPaymentRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    method: PaymentMethodType
    amount_pkr: Decimal = Field(..., gt=0, decimal_places=2)
    # Idempotency key prevents double-charging on network retry.
    # Client must generate a UUID per payment attempt and re-send same key on retry.
    idempotency_key: str = Field(..., min_length=8, max_length=128)


class DownPaymentResponse(BaseModel):
    status: str                              # "pending" | "success"
    order_id: int
    payment_transaction_id: int
    payment_session_url: Optional[str] = None  # Present for SafePay redirect flow
    gateway_txn_id: Optional[str] = None
    idempotency_key: str


class PayInstallmentRequest(BaseModel):
    installment_id: int = Field(..., gt=0)
    method: PaymentMethodType
    payment_method_id: Optional[int] = None   # Saved payment method if applicable


class PayInstallmentResponse(BaseModel):
    success: bool
    txn_id: int
    paid_at: str
    next_installment_id: Optional[int] = None


class RefundRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    amount_pkr: Decimal = Field(..., gt=0, decimal_places=2)
    reason: str = Field(..., min_length=3, max_length=255)
    # Internal refund reference for idempotency
    refund_reference: str = Field(..., min_length=8, max_length=128)


class RefundResponse(BaseModel):
    refund_id: int
    order_id: int
    amount_pkr: Decimal
    status: str                              # "initiated" | "success" | "failed"
    gateway_refund_id: Optional[str] = None
    reason: str


class WebhookAck(BaseModel):
    status: str                              # "ok" | "duplicate" | "ignored"