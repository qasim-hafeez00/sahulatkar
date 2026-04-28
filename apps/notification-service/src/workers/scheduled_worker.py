"""
NS-BL-09: Scheduled Notification Worker

Processes ScheduledNotification records whose scheduled_for time has elapsed.
The ScheduledNotification model and admin endpoints existed but this background
worker was never implemented, meaning scheduled_for was never honoured and
fired_at was never set — all scheduled messages were silently ignored.

Run schedule: every minute (or via cron/APScheduler alongside reminder_worker).
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.database import SessionLocal
from sk_shared.models.notification import ScheduledNotification
from sk_shared.redis_client import get_redis_client

from src.config import settings
from src.services.notification_service import NotificationService

logger = logging.getLogger("scheduled_worker")


async def fire_scheduled_notifications() -> dict:
    """
    Query all pending ScheduledNotification records that are due and create
    the corresponding notifications via NotificationService.

    A scheduled notification is due when:
      - fired_at IS NULL     (not yet fired)
      - cancelled_at IS NULL (not manually cancelled)
      - scheduled_for <= now (due time has elapsed)

    After firing, sets fired_at to the current UTC timestamp.
    """
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    now = datetime.now(timezone.utc)
    stats = {"found": 0, "fired": 0, "errors": 0, "skipped_cancelled": 0}

    async with SessionLocal() as db:
        query = select(ScheduledNotification).where(
            ScheduledNotification.fired_at.is_(None),
            ScheduledNotification.cancelled_at.is_(None),
            ScheduledNotification.scheduled_for <= now,
        ).limit(200)  # Process at most 200 per sweep to avoid long-running transactions

        pending = list((await db.scalars(query)).all())
        stats["found"] = len(pending)

        if not pending:
            return stats

        ns = NotificationService(db=db, redis=redis)

        for scheduled in pending:
            try:
                await ns.create_notification(
                    user_id=scheduled.user_id,
                    event_type=scheduled.event_type,
                    template_vars=scheduled.template_vars or {},
                    idempotency_key=f"scheduled-{scheduled.id}",
                    source_reference=f"scheduled:{scheduled.id}",
                )
                scheduled.fired_at = now
                stats["fired"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.error(
                    "Failed to fire scheduled notification",
                    extra={"scheduled_id": scheduled.id, "error": str(exc)},
                )

        await db.commit()

    logger.info("Scheduled notification sweep complete", extra=stats)
    return stats


async def run_scheduled_worker(interval_seconds: int = 60) -> None:
    """
    Continuous loop: poll for due scheduled notifications every `interval_seconds`.
    Intended to be started as a background asyncio task alongside the main FastAPI app.
    """
    logger.info("Scheduled notification worker started", extra={"interval_seconds": interval_seconds})
    while True:
        try:
            await fire_scheduled_notifications()
        except Exception as exc:
            logger.error("Scheduled worker sweep failed", extra={"error": str(exc)})
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(fire_scheduled_notifications())
