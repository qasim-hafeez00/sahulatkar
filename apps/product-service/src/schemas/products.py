from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    raw_url: str = Field(min_length=8, max_length=2048)


class ExtractionMeta(BaseModel):
    title: str
    brand: str | None = None
    description: str | None = None
    images: list[str] = Field(default_factory=list)


class ExtractionPricing(BaseModel):
    amount: Decimal
    currency: str = "PKR"

class ShippingInfo(BaseModel):
    estimated_cost: Decimal = Decimal("0")
    estimated_days: str = "unknown"
    ships_to_pakistan: bool = True

class VariantOption(BaseModel):
    label: str
    value: str
    is_available: bool = True

class VariantGroup(BaseModel):
    option_name: str
    options: list[VariantOption] = Field(default_factory=list)


class FinancingOffer(BaseModel):
    plan_months: int
    profit_rate_pct: Decimal
    cost_price: Decimal
    profit_amount: Decimal
    total_repayable: Decimal
    down_payment_amount: Decimal
    installment_count: int
    installment_amount: Decimal


class UpoResponse(BaseModel):
    product_id: UUID
    source_url: str
    platform: str
    extraction_method: str
    extraction_confidence: Decimal
    availability: Literal["in_stock", "out_of_stock", "limited", "unknown"]
    is_purchasable: bool
    meta: ExtractionMeta
    pricing: ExtractionPricing
    variants: list[VariantGroup] = Field(default_factory=list)
    shipping: ShippingInfo | None = None


class ExtractResponse(BaseModel):
    status: Literal["completed", "extracting"]
    job_id: UUID | None = None
    upo: UpoResponse | None = None


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    upo: UpoResponse | None = None
    error_code: str | None = None
    error_message: str | None = None


class OfferResponse(BaseModel):
    product_id: UUID
    upo: UpoResponse
    financing_offer: FinancingOffer


class SearchItem(BaseModel):
    product_id: UUID
    name: str
    canonical_url: str | None = None
    currency: str
    cost_price: Decimal
    sale_price: Decimal | None = None


class SearchResponse(BaseModel):
    items: list[SearchItem]
    total: int


class AgentQueueRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    vcn_id: int = Field(..., gt=0)
    correlation_id: str | None = Field(default=None, max_length=128)
    force_failure: bool = False


class AgentQueueResponse(BaseModel):
    status: Literal["queued"]
    job_id: UUID
    estimated_completion_seconds: int
