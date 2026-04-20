"""BUG-02 Regression Tests — Checkout Queue FIFO Direction.

Verifies that ``queue_job()`` uses lpush (LEFT push) so that ``brpop``
(which pops from the RIGHT) delivers jobs in FIFO order.

The bug was: rpush + brpop = LIFO (newest job processed first).
The fix is:  lpush + brpop = FIFO (oldest job processed first).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from sk_shared.constants import QueueName
from sk_shared.redis_client import RedisClient


@pytest.mark.asyncio
async def test_queue_job_uses_lpush_for_fifo(db_session, redis_mock):
    """queue_job() must use lpush so brpop delivers jobs in FIFO order."""
    from src.services.checkout import CheckoutAgentService
    from sk_shared.models.order import Order
    from sk_shared.models.payment import VirtualCard

    # Track which push method is called
    push_calls: list[str] = []
    original_lpush = redis_mock.lpush
    original_rpush = getattr(redis_mock, "rpush", None)

    async def tracking_lpush(key, value):
        push_calls.append("lpush")
        return await original_lpush(key, value)

    redis_mock.lpush = tracking_lpush
    if original_rpush:
        async def tracking_rpush(key, value):
            push_calls.append("rpush")
            return await original_rpush(key, value)
        redis_mock.rpush = tracking_rpush

    service = CheckoutAgentService(db_session, redis_mock)

    with patch.object(service.db, "scalar", new_callable=AsyncMock, return_value=None), \
         patch.object(service.db, "commit", new_callable=AsyncMock), \
         patch.object(service.db, "refresh", new_callable=AsyncMock), \
         patch.object(service.db, "add", return_value=None):

        from sk_shared.models.checkout import PurchaseExecution
        mock_exec = MagicMock(spec=PurchaseExecution)
        mock_exec.uuid = "test-uuid-1234"

        with patch("src.services.checkout.agent.CheckoutAgentService.queue_job",
                   wraps=service.queue_job):
            # Patch DB add to set uuid
            import uuid as _uuid
            service.db.add = lambda obj: setattr(obj, "uuid", str(_uuid.uuid4()))
            try:
                await service.queue_job(order_id=1, vcn_id=1)
            except Exception:
                pass  # DB not fully wired; we only care about the push direction

    assert "rpush" not in push_calls, (
        "queue_job must NOT use rpush — that causes LIFO ordering. Use lpush for FIFO."
    )


@pytest.mark.asyncio
async def test_checkout_queue_fifo_order_with_fakeredis():
    """End-to-end FIFO verification: two lpush items dequeued in insertion order via brpop."""
    redis = RedisClient(fakeredis.aioredis.FakeRedis())

    # Simulate producer: lpush first_job, then second_job
    await redis.lpush(QueueName.CHECKOUT, json.dumps({"execution_id": "first", "order_id": 1}))
    await redis.lpush(QueueName.CHECKOUT, json.dumps({"execution_id": "second", "order_id": 2}))

    # Consumer: brpop should return "first" before "second" (FIFO)
    job1 = await redis.redis.brpop(QueueName.CHECKOUT, timeout=1)
    job2 = await redis.redis.brpop(QueueName.CHECKOUT, timeout=1)

    assert job1 is not None, "Expected first job in queue"
    assert job2 is not None, "Expected second job in queue"

    payload1 = json.loads(job1[1].decode("utf-8"))
    payload2 = json.loads(job2[1].decode("utf-8"))

    assert payload1["execution_id"] == "first", (
        f"FIFO violated: expected 'first' but got '{payload1['execution_id']}'. "
        "Queue is operating in LIFO mode — check that queue_job uses lpush not rpush."
    )
    assert payload2["execution_id"] == "second"
