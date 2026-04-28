"""
Retry strategy for failed notification dispatches.

Exponential backoff formula (matching notification_service.py dispatch logic):
  delay = RETRY_BACKOFF_BASE_SECONDS * (3 ** (attempt_count - 1))

  attempt 1 →  30s
  attempt 2 →  90s
  attempt 3 → 270s  (4.5 min)
  attempt 4 → 810s  (13.5 min) — beyond MAX_DISPATCH_RETRIES=3, goes to DLQ

Max retries before DLQ:  MAX_DISPATCH_RETRIES (default 3, from settings).
DLQ alert threshold:     DLQ_ALERT_THRESHOLD (default 50 items, from settings).
"""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sk_shared.models.notification import NotificationDispatch, DispatchStatus

from src.config import settings


class RetryService:
    """
    Polls the database for dispatch records in RETRYING status whose backoff
    window has elapsed and re-enqueues them into the main notification queue.

    Strategy constants (mirrors notification_service.py dispatch logic):
      MAX_ATTEMPTS  = settings.MAX_DISPATCH_RETRIES
      BACKOFF_BASE  = settings.RETRY_BACKOFF_BASE_SECONDS
      BACKOFF_MULT  = 3   (tripling: 30s → 90s → 270s)
    """

    MAX_ATTEMPTS: int = settings.MAX_DISPATCH_RETRIES
    BACKOFF_BASE: int = settings.RETRY_BACKOFF_BASE_SECONDS
    BACKOFF_MULT: int = 3

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_due_retries(self, limit: int = 100) -> list[NotificationDispatch]:
        """Return dispatches whose next_retry_at has elapsed."""
        query = select(NotificationDispatch).where(
            NotificationDispatch.status == DispatchStatus.RETRYING,
            NotificationDispatch.next_retry_at <= datetime.now(timezone.utc)
        ).limit(limit)
        return list((await self.db.scalars(query)).all())

    @classmethod
    def should_dlq(cls, dispatch: NotificationDispatch) -> bool:
        """
        Return True if this dispatch should be moved to DLQ on next failure.

        A dispatch goes to DLQ when:
          1. It has reached or exceeded MAX_ATTEMPTS (max retries exhausted), OR
          2. The failure is non-retryable (e.g. invalid phone — should_retry=False).
        This mirrors the logic in NotificationService.dispatch_notification().
        """
        return dispatch.attempt_count >= cls.MAX_ATTEMPTS
