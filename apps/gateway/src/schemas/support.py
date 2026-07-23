from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

TICKET_CATEGORIES = (
    "payment_issue",
    "delivery_issue",
    "product_issue",
    "kyc_query",
    "fraud_report",
    "refund_request",
    "contract_query",
    "account_issue",
    "general",
)


class TicketCreateRequest(BaseModel):
    category: str = Field(..., pattern="^(" + "|".join(TICKET_CATEGORIES) + ")$")
    subject: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=5, max_length=4000)
    order_id: Optional[int] = None
    loan_id: Optional[int] = None


class TicketMessageCreateRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class TicketMessageItem(BaseModel):
    id: int
    sender_type: str
    sender_id: Optional[int]
    message_text: str
    created_at: datetime


class TicketSummary(BaseModel):
    id: int
    ticket_number: str
    category: str
    subject: str
    status: str
    order_id: Optional[int]
    loan_id: Optional[int]
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketSummary):
    messages: list[TicketMessageItem]
