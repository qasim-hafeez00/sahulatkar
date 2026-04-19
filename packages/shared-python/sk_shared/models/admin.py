from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, SoftDeleteMixin, TimestampMixin


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
