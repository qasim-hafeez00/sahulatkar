from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from sk_shared.models.base import Base, TimestampMixin


class AuditTrail(Base, TimestampMixin):
    """Application-level audit events (distinct from DB trigger-based row audit)."""

    __tablename__ = "gateway_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    customer_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    changes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
