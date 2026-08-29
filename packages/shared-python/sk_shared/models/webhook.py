from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ProcessedWebhookEvent(Base):
    """DB-backed second layer for inbound-webhook dedup.

    MEDIUM fix: Gateway's webhook dedup (api/v1/webhooks.py's
    _enqueue_webhook) previously relied solely on a 24h Redis SETNX marker
    keyed on idempotency_key. If Redis is unavailable (or the key has
    expired/been evicted) a retried webhook from JazzCash/SafePay/Stripe
    would be re-enqueued and reprocessed with no fallback anywhere. This
    table records every idempotency_key actually enqueued so it can be
    checked when Redis returns no marker for the key -- a durable second
    layer, not a replacement for the fast Redis path.
    """
    __tablename__ = "processed_webhook_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    gateway: Mapped[str] = mapped_column(String(50), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
