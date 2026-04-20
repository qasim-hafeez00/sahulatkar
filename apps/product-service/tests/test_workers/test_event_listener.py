import json
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import select

from sk_shared.models.checkout import PurchaseExecution
import src.workers.event_listener as event_listener_module
from src.workers.event_listener import EventListenerWorker


@pytest.mark.asyncio
async def test_order_cancelled_event_cancels_pending_execution(db_session, redis_mock, monkeypatch):
    execution = PurchaseExecution(
        order_id=9001,
        vcn_id=1,
        status="queued",
        step_reached="queued",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    await db_session.commit()

    class _SessionCtx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(event_listener_module, "SessionLocal", lambda: _SessionCtx())

    worker = EventListenerWorker()
    await worker._handle_order_cancelled({"order_id": 9001}, redis_mock)

    refreshed = await db_session.scalar(select(PurchaseExecution).where(PurchaseExecution.id == execution.id))
    assert refreshed.status == "cancelled"


@pytest.mark.asyncio
async def test_order_cancelled_cleans_queue_and_cancels_running_execution(db_session, redis_mock, monkeypatch):
    execution = PurchaseExecution(
        order_id=9010,
        vcn_id=2,
        status="running",
        step_reached="submit_order",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    await db_session.commit()

    class _SessionCtx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(event_listener_module, "SessionLocal", lambda: _SessionCtx())

    await redis_mock.redis.lpush(
        "sk:queue:checkout",
        json.dumps({"execution_id": str(execution.uuid), "order_id": 9010, "vcn_id": 2}),
    )
    await redis_mock.redis.lpush(
        "sk:queue:checkout",
        json.dumps({"execution_id": str(UUID(int=1)), "order_id": "9010", "vcn_id": 999}),
    )

    worker = EventListenerWorker()
    await worker._handle_order_cancelled({"order_id": 9010}, redis_mock)

    refreshed = await db_session.scalar(select(PurchaseExecution).where(PurchaseExecution.id == execution.id))
    assert refreshed.status == "cancelled"

    remaining = await redis_mock.redis.lrange("sk:queue:checkout", 0, -1)
    assert remaining == []
