from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class ReconciliationRecord(BaseModel):
    """One row from a gateway settlement file."""
    gateway_txn_id: str
    amount_pkr: Decimal
    status: str
    settled_at: datetime


class ReconciliationImportRequest(BaseModel):
    gateway: str                    # "jazzcash" | "safepay" | "raast" | "stripe"
    settlement_date: date
    records: List[ReconciliationRecord]


class ReconciliationItemResult(BaseModel):
    gateway_txn_id: str
    internal_txn_id: Optional[int]
    match_status: str               # "matched" | "amount_mismatch" | "missing_internally" | "missing_in_gateway"
    gateway_amount: Decimal
    internal_amount: Optional[Decimal]
    discrepancy_amount: Optional[Decimal]


class ReconciliationReport(BaseModel):
    gateway: str
    settlement_date: date
    total_records: int
    matched: int
    discrepancies: int
    total_gateway_amount: Decimal
    total_internal_amount: Decimal
    net_discrepancy: Decimal
    items: List[ReconciliationItemResult]
    created_at: datetime
