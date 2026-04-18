from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.schemas.common import PaginationResponse


class ReconciliationImportRequest(BaseModel):
    gateway: str = Field(..., examples=["safepay"])
    settlement_date: date
    expected_amount: Decimal
    actual_amount: Decimal
    reference: str | None = None
    notes: str | None = None


class ProfitLossResponse(BaseModel):
    period: str
    revenue: float
    costs: float
    net_income: float
    margin_pct: float


class TrialBalanceEntryResponse(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    debit_total: float
    credit_total: float


class TrialBalanceResponse(BaseModel):
    period: str
    entries: list[TrialBalanceEntryResponse]
    total_debit: float
    total_credit: float
    is_balanced: bool


class BalanceSheetEntryResponse(BaseModel):
    account_code: str
    account_name: str
    balance: float


class BalanceSheetResponse(BaseModel):
    as_of: str
    assets: list[BalanceSheetEntryResponse]
    liabilities: list[BalanceSheetEntryResponse]
    equity: list[BalanceSheetEntryResponse]
    total_assets: float
    total_liabilities_and_equity: float
    is_balanced: bool


class ReconciliationItemResponse(BaseModel):
    gateway: str | None
    settlement_id: int | None
    transaction_count: int
    total_amount: float
    last_reconciled_at: datetime | None


class ReconciliationSummaryResponse(BaseModel):
    transaction_count: int
    total_amount: float


class ReconciliationListResponse(BaseModel):
    filters: dict[str, str | None]
    items: list[ReconciliationItemResponse]
    pagination: PaginationResponse
    summary: ReconciliationSummaryResponse


class ShariahAuditResponse(BaseModel):
    period: str
    late_fees_allocated: float
    allocations_count: int
    charity_routing_ratio: float


class ReconciliationImportResponse(BaseModel):
    gateway: str
    settlement_date: str
    expected_amount: float
    actual_amount: float
    matched_transaction_count: int
    matched_transaction_amount: float
    discrepancy: float
    reference: str | None
    notes: str | None
    status: str


class CharityOrgSummaryResponse(BaseModel):
    charity_org: str
    total_allocated: float


class CharityReportResponse(BaseModel):
    period: str
    allocated: float
    disbursed: float
    pending: float
    by_org: list[CharityOrgSummaryResponse]


class CharityDisbursementRequest(BaseModel):
    allocation_ids: list[int]
    payment_reference: str
    receipt_s3: str


class CharityDisbursementResponse(BaseModel):
    updated_count: int
    total_amount: float
    status: str
