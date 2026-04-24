from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from sk_shared.models.base import Base, TimestampMixin, UUIDMixin


class RefundStatus(str, Enum):
    INITIATED = "initiated"
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"


class RefundWorkflow(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "refund_workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_payment_workflow_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refund_reference: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    amount_pkr: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RefundStatus] = mapped_column(String(20), nullable=False, default=RefundStatus.INITIATED)
    gateway: Mapped[str] = mapped_column(String(20), nullable=False)
    gateway_refund_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
