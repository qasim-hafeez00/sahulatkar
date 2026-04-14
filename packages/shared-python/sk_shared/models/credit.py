from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from sqlalchemy import String, Integer, Numeric, Boolean, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sk_shared.models.base import Base, TimestampMixin, UUIDMixin

class CreditApplication(Base, TimestampMixin, UUIDMixin):
    __tablename__ = 'credit_applications'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    application_type: Mapped[str] = mapped_column(String(30), nullable=False)
    requested_limit: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    user_data_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    credit_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    bureau_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    approved_limit: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    rejection_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

class RiskAssessment(Base, TimestampMixin, UUIDMixin):
    __tablename__ = 'risk_assessments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    credit_app_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    assessment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    total_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    identity_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    device_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    behavioral_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    bank_statement_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    bureau_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    velocity_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    risk_band: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    recommended_limit: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    down_payment_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    flags: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    explanation: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

class CreditLimitHistory(Base, TimestampMixin):
    __tablename__ = 'credit_limit_history'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    old_limit: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    new_limit: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_type: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_id: Mapped[str] = mapped_column(String(255), nullable=False)

class BlacklistedEntity(Base, TimestampMixin):
    __tablename__ = 'blacklisted_entities'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_value: Mapped[str] = mapped_column(String(255), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    blacklisted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class FraudRule(Base, TimestampMixin):
    __tablename__ = 'fraud_rules'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    condition_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    threshold: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class VelocityCheck(Base, TimestampMixin):
    __tablename__ = 'velocity_checks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    check_type: Mapped[str] = mapped_column(String(50), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    breached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
