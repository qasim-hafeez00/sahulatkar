from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CheckoutVariant(BaseModel):
    option_name: str
    selected_value: str


class CheckoutJobDetailResponse(BaseModel):
    execution_id: UUID
    order_id: int
    vcn_id: int | None = None
    status: str
    step_reached: str | None = None
    attempt_number: int
    merchant_order_id: str | None = None
    failure_type: str | None = None
    error_detail: str | None = None
    screenshot_urls: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None


class ExecutionRetryRequest(BaseModel):
    reason: str


class ExecutionListResponse(BaseModel):
    items: list[CheckoutJobDetailResponse]
    total: int
