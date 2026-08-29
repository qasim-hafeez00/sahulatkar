from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.hitl import HitlQueue
from sk_shared.redis_client import RedisClient
from src.config import settings
from src.core.logging import logger

_OPEN_STATUSES = ("pending", "claimed", "in_progress")


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def sweep_hitl_sla_breaches(db: AsyncSession, redis: RedisClient | None = None) -> list[HitlQueue]:
    """HIGH-3 fix: HitlQueue.sla_deadline was stored (internal.py) and
    displayed (admin_hitl.py's _serialize) but nothing anywhere ever checked
    it against "now" and raised an alert — a case could blow through its SLA
    deadline silently, forever, with no escalation to anyone.

    This finds every still-open (pending/claimed/in_progress) HITL item
    whose sla_deadline has passed and logs a structured CRITICAL alert for
    each one. No dedicated paging/Slack/PagerDuty integration exists
    anywhere in this codebase today (confirmed by repo-wide search) —
    structured logger.critical()/logger.error() with extra={} fields is the
    established "operational alert" convention here (see e.g.
    payment-orchestrator's vcn_expiry_worker.py and outbox_publisher.py),
    which a log-based alert rule (CloudWatch/Loki/etc, already deployed per
    infra/k8s/base/logging) can page on.

    Dedup via Redis (same SETNX-with-TTL pattern as the event dedup in
    main.py's delivery_event_listener, and the AfterShip webhook dedup in
    notification-service) so a still-unresolved item is re-alerted at most
    once per settings.HITL_SLA_ALERT_DEDUP_SECONDS, not once per sweep
    interval forever. `redis` is optional so this stays trivially callable
    from a one-off script/tests without a Redis dependency -- omitting it
    just means every breach is logged every sweep run instead of deduped.
    """
    now = datetime.now(timezone.utc)

    # Compare in Python, not SQL: sla_deadline is a naive DateTime column
    # (see sk_shared.models.hitl.HitlQueue) fed by an aware
    # datetime.now(timezone.utc) at write time (internal.py) -- an
    # inequality pushed down to SQL risks a naive/aware mismatch depending
    # on backend (SQLite stores it as a plain string; Postgres has no
    # timezone info to reason about either). Same normalize-then-compare
    # approach ContractSignerService._check_validity already uses.
    candidates = (
        await db.execute(
            select(HitlQueue).where(
                HitlQueue.status.in_(_OPEN_STATUSES),
                HitlQueue.sla_deadline.is_not(None),
            )
        )
    ).scalars().all()

    breached = [item for item in candidates if _as_utc(item.sla_deadline) < now]

    for item in breached:
        if redis is not None and hasattr(redis, "redis"):
            dedup_key = f"sk:hitl:sla_alerted:{item.id}"
            claimed = await redis.redis.set(
                dedup_key, "1", nx=True, ex=settings.HITL_SLA_ALERT_DEDUP_SECONDS
            )
            if not claimed:
                continue

        deadline = _as_utc(item.sla_deadline)
        overdue_seconds = (now - deadline).total_seconds()

        logger.critical(
            "HITL_SLA_BREACH queue_id=%s order_id=%s priority=%s status=%s overdue_seconds=%.0f",
            item.id, item.order_id, item.priority, item.status, overdue_seconds,
            extra={
                "hitl_queue_id": item.id,
                "order_id": item.order_id,
                "execution_id": item.execution_id,
                "priority": item.priority,
                "status": item.status,
                "assigned_to": item.assigned_to,
                "sla_deadline": deadline.isoformat(),
                "overdue_seconds": overdue_seconds,
            },
        )

    return breached
