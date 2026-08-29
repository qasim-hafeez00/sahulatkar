from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from sk_shared.models.order import Order
from src.config import settings
from src.services.order_recovery_sweep import sweep_stuck_orders
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


async def _seed_order(user_id: int, *, age_seconds: float, status: str = "url_received") -> Order:
    async with TestingSessionLocal() as session:
        order = Order(
            user_id=user_id,
            status=status,
            total_amount=0,
            product_description="https://example.com/p/1",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def test_sweep_stuck_orders_marks_timed_out_order_extraction_failed(test_user, db_session):
    """HIGH-4 regression: an order that has sat at 'url_received' longer than
    ORDER_STUCK_EXTRACTION_TIMEOUT_SECONDS must be proactively recovered by
    the sweep -- not only when a customer happens to poll GET /orders/{id}/offer.
    """
    user, _token = test_user
    stuck_order = await _seed_order(
        user.id, age_seconds=settings.ORDER_STUCK_EXTRACTION_TIMEOUT_SECONDS + 60
    )

    recovered = await sweep_stuck_orders(db_session)

    assert recovered == [stuck_order.id]

    async with TestingSessionLocal() as session:
        refreshed = await session.get(Order, stuck_order.id)
        assert refreshed.status == "extraction_failed"


async def test_sweep_stuck_orders_leaves_fresh_order_alone(test_user, db_session):
    """A freshly-created 'url_received' order (well within the timeout) must
    not be touched by the sweep."""
    user, _token = test_user
    fresh_order = await _seed_order(user.id, age_seconds=5)

    recovered = await sweep_stuck_orders(db_session)

    assert fresh_order.id not in recovered

    async with TestingSessionLocal() as session:
        refreshed = await session.get(Order, fresh_order.id)
        assert refreshed.status == "url_received"


async def test_sweep_stuck_orders_only_recovers_stuck_and_skips_fresh_together(test_user, db_session):
    """Mixed batch: sweep must recover exactly the stuck order and leave the
    fresh order untouched in the same run."""
    user, _token = test_user
    stuck_order = await _seed_order(
        user.id, age_seconds=settings.ORDER_STUCK_EXTRACTION_TIMEOUT_SECONDS + 120
    )
    fresh_order = await _seed_order(user.id, age_seconds=1)

    recovered = await sweep_stuck_orders(db_session)

    assert stuck_order.id in recovered
    assert fresh_order.id not in recovered

    async with TestingSessionLocal() as session:
        stuck_refreshed = await session.get(Order, stuck_order.id)
        fresh_refreshed = await session.get(Order, fresh_order.id)
        assert stuck_refreshed.status == "extraction_failed"
        assert fresh_refreshed.status == "url_received"
