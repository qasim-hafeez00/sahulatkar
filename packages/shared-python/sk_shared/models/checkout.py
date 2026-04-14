from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDMixin


class PurchaseExecution(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "purchase_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    vcn_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("virtual_cards.id", ondelete="SET NULL"), nullable=True)
    attempt_number: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    worker_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    proxy_used: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    step_reached: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    failure_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_s3: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    merchant_order_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    merchant_order_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    receipt_screenshot_s3: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_purchase_executions_order_created", "order_id", "created_at"),
        Index("ix_purchase_executions_status_created", "status", "created_at"),
    )