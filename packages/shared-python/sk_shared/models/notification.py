from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sk_shared.models.base import Base

class NotificationCategory(str, Enum):
    AUTH = "auth"
    KYC = "kyc"
    CREDIT = "credit"
    ORDER = "order"
    CONTRACT = "contract"
    PAYMENT = "payment"
    DELIVERY = "delivery"
    BILLING = "billing"
    COMPLIANCE = "compliance"    # Shariah disclosures, charity confirmations
    SYSTEM = "system"

class NotificationPriority(str, Enum):
    CRITICAL = "critical"   # OTPs — bypass rate limits, immediate dispatch
    HIGH = "high"           # Payment confirms, delivery updates
    NORMAL = "normal"       # Reminders, offers
    LOW = "low"             # Marketing (post-MVP)

class NotificationStatus(str, Enum):
    QUEUED = "queued"
    DISPATCHING = "dispatching"
    DELIVERED = "delivered"     # At least one channel delivered
    FAILED = "failed"           # All channels failed
    CANCELLED = "cancelled"

class DispatchChannel(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PUSH = "push"
    EMAIL = "email"

class DispatchStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"           # Accepted by provider
    DELIVERED = "delivered" # Confirmed by delivery receipt
    FAILED = "failed"
    RETRYING = "retrying"
    DLQ = "dlq"

class Notification(Base):
    __tablename__ = "notifications"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    
    # Correlation back to the source event
    source_event: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "payment.down_payment_confirmed"
    source_reference: Mapped[Optional[str]] = mapped_column(String(200))     # e.g. "order:12345"
    
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # NotificationCategory
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    
    # Resolved content (after template rendering, before channel-specific formatting)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Read tracking (for the in-app inbox)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Aggregate status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    
    # Idempotency — prevents duplicate notifications from duplicate events
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    
    # Channels attempted for this notification
    channels_requested: Mapped[list] = mapped_column(JSON, nullable=False)
    
    # Template variables for per-channel rendering
    template_vars: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)  # OTPs expire, some reminders expire

    dispatches: Mapped[list["NotificationDispatch"]] = relationship(back_populates="notification")
    user = relationship("User")

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_status", "status"),
        Index("ix_notifications_source_event", "source_event"),
    )


class NotificationDispatch(Base):
    """
    One row per channel attempt for a given Notification.
    A Notification may have SMS + WhatsApp dispatches simultaneously.
    """
    __tablename__ = "notification_dispatches"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    notification_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("notifications.id"), nullable=False, index=True)
    
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # DispatchChannel
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    
    # Provider-specific message ID (for delivery receipt correlation)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    provider_name: Mapped[Optional[str]] = mapped_column(String(50))  # e.g. "jazz_sms", "twilio", "fcm"
    
    # Channel-specific rendered content
    rendered_content: Mapped[Optional[str]] = mapped_column(Text)
    
    # Delivery tracking
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Retry tracking
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    notification: Mapped["Notification"] = relationship(back_populates="dispatches")

    __table_args__ = (
        UniqueConstraint("notification_id", "channel", name="uq_dispatch_notification_channel"),
        Index("ix_dispatch_status_retry", "status", "next_retry_at"),
    )


class NotificationTemplate(Base):
    """
    Per-channel, per-event message templates.
    Uses Jinja2 syntax with platform-standard variables.
    """
    __tablename__ = "notification_templates"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)   # source_event value
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")  # "en" or "ur"
    
    subject: Mapped[Optional[str]] = mapped_column(String(255))  # email subject
    body_template: Mapped[str] = mapped_column(Text, nullable=False)  # Jinja2 template
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"))

    __table_args__ = (
        UniqueConstraint("event_type", "channel", "language", name="uq_template_event_channel_lang"),
    )


class NotificationPreference(Base):
    """
    User's channel opt-in/out preferences per notification category.
    Defaults to all channels enabled. Compliance categories (AUTH, COMPLIANCE)
    cannot be opted out.
    """
    __tablename__ = "notification_preferences"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Global flag — if True, overrides all category-specific settings (except compliance/auth)
    is_globally_unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_pref_user_category"),
    )


class ScheduledNotification(Base):
    """
    Future-dated notifications (installment reminders, overdue escalation).
    The reminder_worker processes rows where fire_at <= now().
    """
    __tablename__ = "scheduled_notifications"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    fire_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    
    # Idempotency key to prevent double-firing
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    
    fired_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_scheduled_fire_at_fired", "fire_at", "fired_at"),
    )
