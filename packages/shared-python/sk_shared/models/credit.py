from typing import Optional, List, Dict, Any
from datetime import date, datetime
import uuid
from sqlalchemy import BigInteger, String, Integer, Numeric, Boolean, JSON, DateTime, Date, SmallInteger, Text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
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
    user_id: Mapped[int] = mapped_column(nullable=False)
    old_limit: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    new_limit: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_type: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Gateway (orders.py / cart_service.py / internal.py credit-result callback) writes and
    # reads this same table under a second, overlapping field naming convention. Both shapes
    # are kept on one row so every existing caller — credit-engine's old_limit/new_limit/
    # reason_code/changed_by_type/changed_by_id writers and gateway's previous_limit/
    # available_before/available_after/reason/changed_by writers and readers — works against
    # the same table without a cross-service migration.
    previous_limit: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    available_before: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    available_after: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    changed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

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


# ── Tables created by migration 014_credit_risk_remaining, never given ORM models ──────────
# (fraud_alerts, manual_review_queue, bank_statement_analysis, device_fingerprints,
# ip_intelligence, synthetic_identity_indicators) or migration 031 (credit_scores_history).
# Column shapes here mirror those migrations exactly — see db/migrations/versions/014_* / 031_*.

class FraudAlert(Base, UUIDMixin):
    __tablename__ = 'fraud_alerts'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    order_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    payment_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # alert_type check constraint: synthetic_identity|account_takeover|velocity_breach|
    # device_anomaly|collusion_merchant|sim_swap_suspected|cross_border_risk|bot_detection|
    # document_forgery|address_mismatch
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # severity check constraint: low|medium|high|critical
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    # source check constraint: rule_engine|ml_model|manual|watchlist
    source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    rule_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # status check constraint: open|investigating|resolved_genuine|resolved_fraud|false_positive
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='open')
    investigated_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_taken: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ManualReviewQueueItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = 'manual_review_queue'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    queue_type: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    assigned_to: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # status check constraint: pending|in_review|resolved|escalated
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='pending')
    sla_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class BankStatementAnalysis(Base, UUIDMixin):
    __tablename__ = 'bank_statement_analysis'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    avg_balance: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    income_estimate: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    expense_ratio: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    salary_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nsf_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    raw_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class DeviceFingerprint(Base, UUIDMixin):
    __tablename__ = 'device_fingerprints'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_fingerprint: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    computed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_flags: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    is_known_fraud_device: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class IpIntelligence(Base):
    __tablename__ = 'ip_intelligence'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(INET().with_variant(String(45), "sqlite"), unique=True, nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    isp: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_proxy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_vpn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_tor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    threat_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    looked_up_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class SyntheticIdentityIndicator(Base):
    __tablename__ = 'synthetic_identity_indicators'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    indicator_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    supporting_signals: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    flagged_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class CreditScoreHistory(Base):
    __tablename__ = 'credit_scores_history'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


# ── New in this redesign: versioned rule/scorecard config + per-assessment feature snapshots ──

class CreditPolicyVersion(Base, UUIDMixin, TimestampMixin):
    """A versioned, auditable snapshot of every tunable in the decision engine: prohibited
    categories, category/merchant risk multipliers, scorecard point weights, thresholds, cold
    start caps. Replaces the hardcoded dicts previously duplicated across layer1/layer6.
    Exactly one row has status='active' at a time; RulePolicy loads and Redis-caches it."""
    __tablename__ = 'credit_policy_versions'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_label: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    # status check constraint: draft|active|retired
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='draft')
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class CreditFeatureSnapshot(Base, UUIDMixin, TimestampMixin):
    """The exact feature vector + additive score-breakdown used for one assessment, frozen at
    decision time. Powers /credit/explanation today and is the future training set for a
    trained model — outcome labels (repaid/defaulted) get joined onto this by user_id+time
    once loans mature, without re-deriving what the engine saw at decision time."""
    __tablename__ = 'credit_feature_snapshots'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    assessment_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    features: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    score_breakdown: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    policy_version: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
