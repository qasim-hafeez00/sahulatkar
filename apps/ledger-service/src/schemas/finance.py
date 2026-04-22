from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.schemas.common import PaginationResponse


class ReconciliationImportRequest(BaseModel):
    gateway: str = Field(..., examples=["safepay"])
    settlement_date: date
    expected_amount: Decimal = Field(..., ge=0)
    actual_amount: Decimal = Field(..., ge=0)
    reference: str | None = None
    notes: str | None = None

    @field_validator("gateway")
    @classmethod
    def validate_gateway(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("gateway must not be empty")
        return trimmed


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


class LedgerAccountSummaryResponse(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    normal_balance: str
    is_active: bool
    debit_total: float
    credit_total: float
    balance: float


class LedgerAccountsListResponse(BaseModel):
    as_of: str
    account_type_filter: str | None
    items: list[LedgerAccountSummaryResponse]


class AccountBalanceResponse(BaseModel):
    as_of: str
    account_code: str
    account_name: str
    account_type: str
    normal_balance: str
    is_active: bool
    debit_total: float
    credit_total: float
    balance: float


class JournalEntryLineResponse(BaseModel):
    account_code: str
    account_name: str
    debit_amount: float
    credit_amount: float
    description: str | None


class JournalEntryResponse(BaseModel):
    entry_number: str
    entry_date: str
    entry_type: str
    source_type: str | None
    source_id: int | None
    description: str
    total_debit: float
    total_credit: float
    is_balanced: bool
    lines: list[JournalEntryLineResponse]


class JournalEntryListFiltersResponse(BaseModel):
    from_date: str | None
    to_date: str | None
    entry_type: str | None
    source_type: str | None


class CursorPaginationResponse(BaseModel):
    limit: int
    next_cursor: str | None
    has_more: bool


class JournalEntryListResponse(BaseModel):
    filters: JournalEntryListFiltersResponse
    pagination: CursorPaginationResponse
    items: list[JournalEntryResponse]


class ARAgingBucketResponse(BaseModel):
    bucket: str
    count: int
    total_amount: float


class ARAgingFiltersResponse(BaseModel):
    user_id: int | None
    plan_type: str | None
    status: str | None


class ARAgingResponse(BaseModel):
    as_of: str
    filters: ARAgingFiltersResponse
    items: list[ARAgingBucketResponse]
    total_outstanding: float


class DLQMessageResponse(BaseModel):
    message_id: int
    event_name: str
    payload: dict[str, Any] | str
    error_type: str
    error_message: str
    timestamp: datetime
    retry_count: int


class DLQListResponse(BaseModel):
    total_messages: int
    items: list[DLQMessageResponse]


class DLQRetryResponse(BaseModel):
    message_id: int
    event_name: str
    status: str


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
    allocation_ids: list[int] = Field(..., min_length=1)
    payment_reference: str
    receipt_s3: str

    @field_validator("allocation_ids")
    @classmethod
    def validate_allocation_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value):
            raise ValueError("allocation_ids must contain positive integers")
        if len(value) != len(set(value)):
            raise ValueError("allocation_ids must not contain duplicates")
        return value

    @field_validator("payment_reference", "receipt_s3")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field must not be empty")
        return trimmed


class CharityDisbursementResponse(BaseModel):
    updated_count: int
    total_amount: float
    status: str
