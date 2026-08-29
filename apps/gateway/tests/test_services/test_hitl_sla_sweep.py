from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from sk_shared.models.hitl import HitlQueue
from sk_shared.models.order import Order
from src.services.hitl_sla_sweep import sweep_hitl_sla_breaches
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


async def _seed_breached_hitl_item(user_id: int, *, overdue_seconds: float = 3600) -> HitlQueue:
    async with TestingSessionLocal() as session:
        order = Order(user_id=user_id, status="purchase_failed", total_amount=1000)
        session.add(order)
        await session.flush()

        hitl = HitlQueue(
            order_id=order.id,
            status="pending",
            priority=2,
            failure_reason="card_declined",
            sla_deadline=datetime.now(timezone.utc) - timedelta(seconds=overdue_seconds),
        )
        session.add(hitl)
        await session.commit()
        await session.refresh(hitl)
        return hitl


async def test_sweep_hitl_sla_breaches_finds_open_item_past_deadline_and_alerts(test_user, db_session):
    """HIGH-3 regression: an open (pending/claimed/in_progress) HITL item
    whose sla_deadline has passed must be found by the sweep and logged as
    a CRITICAL alert -- previously sla_deadline was stored and displayed but
    nothing anywhere ever checked it against "now"."""
    user, _token = test_user
    breached = await _seed_breached_hitl_item(user.id)

    with patch("src.services.hitl_sla_sweep.logger") as mock_logger:
        result = await sweep_hitl_sla_breaches(db_session)

    assert [item.id for item in result] == [breached.id]
    mock_logger.critical.assert_called_once()
    # The structured alert must identify the actual breached item.
    _, call_kwargs = mock_logger.critical.call_args
    assert call_kwargs["extra"]["hitl_queue_id"] == breached.id


async def test_sweep_hitl_sla_breaches_ignores_item_within_sla(test_user, db_session):
    user, _token = test_user
    async with TestingSessionLocal() as session:
        order = Order(user_id=user.id, status="purchase_failed", total_amount=1000)
        session.add(order)
        await session.flush()
        hitl = HitlQueue(
            order_id=order.id,
            status="pending",
            priority=2,
            failure_reason="card_declined",
            sla_deadline=datetime.now(timezone.utc) + timedelta(hours=4),
        )
        session.add(hitl)
        await session.commit()

    result = await sweep_hitl_sla_breaches(db_session)
    assert result == []


async def test_sweep_hitl_sla_breaches_ignores_resolved_item(test_user, db_session):
    """A HITL item past its sla_deadline but already resolved must not be
    treated as an active breach."""
    user, _token = test_user
    async with TestingSessionLocal() as session:
        order = Order(user_id=user.id, status="purchase_confirmed", total_amount=1000)
        session.add(order)
        await session.flush()
        hitl = HitlQueue(
            order_id=order.id,
            status="resolved",
            priority=2,
            failure_reason="card_declined",
            sla_deadline=datetime.now(timezone.utc) - timedelta(hours=2),
            resolution="manually_retried",
        )
        session.add(hitl)
        await session.commit()

    result = await sweep_hitl_sla_breaches(db_session)
    assert result == []


async def test_sweep_hitl_sla_breaches_dedup_via_redis_suppresses_realert(test_user, db_session, redis_mock):
    """A still-unresolved breach must still be returned by every sweep run
    (so callers/metrics see it as ongoing), but must only be logged/alerted
    once per HITL_SLA_ALERT_DEDUP_SECONDS window -- not once per sweep
    interval forever."""
    user, _token = test_user
    breached = await _seed_breached_hitl_item(user.id)

    with patch("src.services.hitl_sla_sweep.logger") as mock_logger:
        first_run = await sweep_hitl_sla_breaches(db_session, redis_mock)
        assert [item.id for item in first_run] == [breached.id]
        assert mock_logger.critical.call_count == 1

        second_run = await sweep_hitl_sla_breaches(db_session, redis_mock)
        # Still reported as an ongoing breach...
        assert [item.id for item in second_run] == [breached.id]
        # ...but not re-alerted within the dedup window.
        assert mock_logger.critical.call_count == 1
