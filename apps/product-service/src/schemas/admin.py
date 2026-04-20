from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class ProhibitedCategoryCreateRequest(BaseModel):
    category_name: str = Field(min_length=2, max_length=100)
    keywords: list[str] = Field(min_length=1)
    shariah_basis: str | None = Field(default=None, max_length=500)


class AdminProductItem(BaseModel):
    product_id: str
    name: str
    platform: str | None = None
    extraction_method: str | None = None
    confidence: str | None = None
    cost_price: str
    created_at: str | None = None


class AdminProductListResponse(BaseModel):
    items: list[AdminProductItem]
    total: int
    next_cursor: str | None = None


class AdminProductDetailItem(BaseModel):
    uuid: str
    name: str
    platform: str | None = None
    url: str
    canonical_url: str | None = None
    cost_price: str
    is_prohibited: bool
    prohibition_reason: str | None = None
    deleted_at: str | None = None


class AdminScrapingJobItem(BaseModel):
    job_id: str
    status: str
    attempt_number: int
    error_code: str | None = None
    created_at: str | None = None


class AdminCheckoutExecutionItem(BaseModel):
    execution_id: str
    status: str
    step_reached: str | None = None
    merchant_order_id: str | None = None
    created_at: str | None = None


class AdminProductDetailResponse(BaseModel):
    product: AdminProductDetailItem
    scraping_jobs: list[AdminScrapingJobItem]
    checkout_executions: list[AdminCheckoutExecutionItem]


class AdminProductActionResponse(BaseModel):
    status: str
    product_id: str


class AdminProductPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, max_length=2048)
    canonical_url: str | None = Field(default=None, max_length=2048)
    platform: str | None = Field(default=None, max_length=30)
    cost_price: Decimal | None = None
    sale_price: Decimal | None = None
    stock_status: str | None = Field(default=None, max_length=20)
    in_stock: bool | None = None
    extraction_method: str | None = Field(default=None, max_length=30)


class AdminExecutionListItem(BaseModel):
    execution_id: str
    order_id: int
    vcn_id: int | None = None
    status: str
    step_reached: str | None = None
    attempt_number: int


class AdminExecutionListResponse(BaseModel):
    items: list[AdminExecutionListItem]
    total: int
    next_cursor: str | None = None


class AdminExecutionDetailResponse(BaseModel):
    execution_id: str
    order_id: int
    vcn_id: int | None = None
    status: str
    step_reached: str | None = None
    attempt_number: int
    merchant_order_id: str | None = None
    failure_type: str | None = None
    error_detail: str | None = None
    screenshot_urls: list[str]
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None


class AdminExecutionRetryResponse(BaseModel):
    status: str
    execution_id: str


class AdminScrapingJobsListItem(BaseModel):
    job_id: str
    status: str
    platform: str | None = None


class AdminScrapingJobsListResponse(BaseModel):
    items: list[AdminScrapingJobsListItem]
    total: int
    next_cursor: str | None = None


class ProhibitedCategoryItem(BaseModel):
    id: int
    category_name: str
    keywords: list[str]
    shariah_basis: str | None = None


class ProhibitedCategoryListResponse(BaseModel):
    items: list[ProhibitedCategoryItem]


class ProhibitedCategoryUpsertResponse(BaseModel):
    status: str
    id: int


class ProhibitedCategoryDeleteResponse(BaseModel):
    status: str
    category_id: int


class QueueStatsResponse(BaseModel):
    checkout_queue_depth: int
    scraping_queue_depth: int
    checkout_dlq_depth: int
    scraping_dlq_depth: int
    checkout_dlq_entries: list[dict] = Field(default_factory=list)
    scraping_dlq_entries: list[dict] = Field(default_factory=list)


class DlqReprocessResponse(BaseModel):
    status: str
    item_id: str
    queue: str
    entry_index: int


class DlqPurgeResponse(BaseModel):
    purged: int
    queue: str


class MerchantItem(BaseModel):
    merchant_id: int
    domain: str
    name: str
    platform: str | None = None
    status: str
    is_active: bool
    checkout_success_rate: str | None = None
    product_count: int


class MerchantListResponse(BaseModel):
    items: list[MerchantItem]
    total: int
    next_cursor: str | None = None


class MerchantBlockResponse(BaseModel):
    status: str
    domain: str
    affected_products: int