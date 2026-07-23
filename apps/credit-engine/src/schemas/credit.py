from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CreditCheckRequest(BaseModel):
    user_id: str
    order_amount: float = Field(gt=0)
    product_category: str = "general"
    is_first_order: bool = False


class CreditCheckResponse(BaseModel):
    approved: bool
    outcome: str = "approved"
    risk_band: str
    approved_limit: float
    down_payment_pct: float
    rejection_reason: str | None
    manual_review_required: bool = False
    requested_amount: float | None = None
    suggested_down_payment_pct: float | None = None
    processing_time_ms: int
    explanation: dict[str, Any]


class CreditEvaluateRequest(BaseModel):
    user_id: str
    order_amount: float = Field(gt=0)
    product_category: str = "general"
    is_first_order: bool = False
    device_fingerprint_hash: str | None = None


class CreditApplyRequest(BaseModel):
    user_id: str
    requested_limit: float = Field(gt=0)
    application_type: Literal[
        "onboarding",
        "limit_increase",
        "limit_review",
        "manual_request",
        "periodic_review",
    ] = "manual_request"
    order_amount: float = Field(gt=0)
    product_category: str = "general"
    is_first_order: bool = False
    device_fingerprint_hash: str | None = None


class CreditApplyResponse(BaseModel):
    application_id: str
    status: str
    approved_limit: float | None
    risk_band: str | None
    rejection_reason: str | None
    manual_review_required: bool = False
    outcome: str | None = None
    suggested_down_payment_pct: float | None = None


class PrequalifyRequest(BaseModel):
    user_id: str
    product_category: str = "general"


class PrequalifyResponse(BaseModel):
    eligible: bool
    reason: str | None
    indicative_limit: float
    down_payment_pct: float | None
    risk_band: str | None
    processing_time_ms: int


class CreditScoreResponse(BaseModel):
    user_id: str
    risk_band: str
    score: float
    identity_score: float
    alt_data_score: float
    model_version: str


class CreditHistoryItem(BaseModel):
    application_id: str
    application_type: str
    status: str
    requested_limit: float | None
    approved_limit: float | None
    rejection_reason: str | None
    decided_by: str | None
    created_at: datetime


class CreditHistoryResponse(BaseModel):
    user_id: str
    applications: list[CreditHistoryItem]


class RecalculateResponse(BaseModel):
    user_id: str
    current_limit: float
    recalculated_limit: float
    risk_band: str
    limit_increased: bool
    delta: float


class CreditStatusItem(BaseModel):
    assessed_at: datetime
    risk_band: str | None
    approved_limit: float | None
    score: float | None


class CreditStatusResponse(BaseModel):
    user_id: str
    current_limit: float
    utilized_amount: float
    available_limit: float
    assessments: list[CreditStatusItem]


class CreditOverrideRequest(BaseModel):
    user_id: str
    new_limit: float = Field(gt=0)
    reason_code: str
    notes: str | None = None
    admin_id: str = "system"


class CreditOverrideResponse(BaseModel):
    status: str
    user_id: str
    new_limit: float
    reason_code: str


class BlacklistRequest(BaseModel):
    entity_type: str
    entity_value: str
    reason_code: str
    severity: str = "high"
    blacklisted_by: str = "system"


class BlacklistResponse(BaseModel):
    status: str
    entity_type: str
    entity_value: str
    reason_code: str
    severity: str
    active: bool


class RiskAlertItem(BaseModel):
    assessment_id: str
    user_id: str
    risk_band: str | None
    score: float | None
    flags: list[str]
    created_at: datetime


class RiskAlertsResponse(BaseModel):
    alerts: list[RiskAlertItem]


class CreditExplanationResponse(BaseModel):
    assessment_id: str
    found: bool
    explanation: dict[str, Any] | None
    flags: list[str]
    model_version: str | None
