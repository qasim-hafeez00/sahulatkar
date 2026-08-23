from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, HttpUrl


class OrderInitiateRequest(BaseModel):
    product_url: HttpUrl


class OrderInitiateResponse(BaseModel):
    order_id: int
    status: str
    estimated_seconds: int = 30


class OfferPlan(BaseModel):
    installment_count: int
    profit_rate_pct: float


class OrderOfferResponse(BaseModel):
    status: Literal["pending", "ready", "declined", "extraction_failed"]
    order_id: int
    product: Optional[dict] = None
    financing: Optional[dict] = None
    reason: Optional[str] = None


class OrderAcceptRequest(BaseModel):
    installment_count: Literal[3, 4, 6, 12] = 4


class OrderSummary(BaseModel):
    id: int
    status: str
    total_amount: float
    down_payment_amount: Optional[float] = None
    installment_count: Optional[int] = None
    created_at: datetime


class OrderDetailResponse(OrderSummary):
    product_id: Optional[int] = None
    product_description: Optional[str] = None
