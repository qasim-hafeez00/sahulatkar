from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class RiskBlacklist(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "risk_blacklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        Index("ix_risk_blacklist_entry_type", "entry_type"),
        Index("ix_risk_blacklist_value", "value"),
    )


class SystemParameter(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "system_parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    param_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    param_value: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_system_parameters_param_key", "param_key"),
    )


class AdminApprovalRequest(Base, UUIDMixin):
    """Generic manager-approval workflow — credit-limit increases, restructuring, etc."""

    __tablename__ = "admin_approval_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    decided_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_admin_approval_requests_status_created_at", "status", "created_at"),
        Index("ix_admin_approval_requests_entity", "entity_type", "entity_id"),
    )
