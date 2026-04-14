from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDMixin


class HitlQueue(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "hitl_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    execution_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("purchase_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    assigned_to: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_s3: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    in_progress_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sla_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_hitl_queue_status_priority", "status", "priority"),
        Index("ix_hitl_queue_assigned_status", "assigned_to", "status"),
        Index("ix_hitl_queue_sla_deadline", "sla_deadline"),
    )