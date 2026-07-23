import json
from unittest.mock import AsyncMock

import pytest

from src.events.publisher import CreditEventPublisher, _DLQ_KEY


@pytest.mark.asyncio
async def test_publish_success_does_not_touch_dlq(redis_mock):
    publisher = CreditEventPublisher(redis_mock)
    await publisher.publish_rejected(user_id="u1", assessment_id=None, reason="test", flags=[])
    assert await redis_mock.llen(_DLQ_KEY) == 0


@pytest.mark.asyncio
async def test_publish_failure_writes_to_dead_letter_queue(redis_mock, monkeypatch):
    # A dropped credit.approved/fraud.detected event used to be silently lost — a Redis
    # publish failure must now leave a replayable record instead.
    monkeypatch.setattr(redis_mock, "publish", AsyncMock(side_effect=ConnectionError("boom")))

    publisher = CreditEventPublisher(redis_mock)
    await publisher.publish_approved(
        user_id="u1", assessment_id=None, risk_band="B", approved_limit=15000.0, down_payment_pct=25.0,
    )

    assert await redis_mock.llen(_DLQ_KEY) == 1
    dlq_items = await redis_mock.lrange(_DLQ_KEY, 0, -1)
    dead_letter = json.loads(dlq_items[0])
    assert dead_letter["event"] == "credit.approved"
    assert dead_letter["payload"]["user_id"] == "u1"
