from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class TransactionSummary(BaseModel):
    id: int
    order_id: Optional[int]
    user_id: int
    amount: Decimal
    currency: str
    gateway: str
    gateway_txn_id: Optional[str]
    status: str
    created_at: Optional[datetime]
    reconciled_at: Optional[datetime]


class PaginatedTransactions(BaseModel):
    items: List[TransactionSummary]
    total: int
    page: int
    page_size: int


class GatewayHealthSummary(BaseModel):
    gateway: str
    failure_count_window: int
    is_degraded: bool
    window_seconds: int


class AdjustmentRequest(BaseModel):
    order_id: int
    amount_pkr: Decimal
    reason: str


class VcnAdminSummary(BaseModel):
    vcn_id: int
    order_id: int
    user_id: int
    status: str
    masked_number: str
    authorized_amount: float
    charged_amount: float
    issued_at: datetime
    expires_at: datetime
    void_reason: Optional[str]
