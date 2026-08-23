from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from sk_shared.models.base import Base, TimestampMixin, UUIDMixin


class OutboxEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending, published, failed
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    def mark_published(self):
        self.status = "published"
        self.published_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str):
        self.status = "failed"
        self.last_error = error
        self.retry_count += 1
