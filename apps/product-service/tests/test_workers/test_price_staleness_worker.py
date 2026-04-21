from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sk_shared.constants import QueueName
from src.config import settings
from src.workers.price_staleness_worker import PriceStalenessWorker


class _SingleSessionFactory:
    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_price_staleness_worker_requeues_stale_products(monkeypatch, db_session, redis_mock, make_product):
    product = await make_product(
        db_session,
        updated_at=datetime.now(timezone.utc) - timedelta(days=2),
        status="active",
        is_prohibited=False,
    )
    await db_session.commit()

    monkeypatch.setattr("src.workers.price_staleness_worker.SessionLocal", _SingleSessionFactory(db_session))
    monkeypatch.setattr(settings, "PRODUCT_STALE_AFTER_SECONDS", 1)
    monkeypatch.setattr(settings, "PRODUCT_STALENESS_BATCH_SIZE", 10)

    worker = PriceStalenessWorker(redis_mock)
    await worker._run_once()

    await db_session.refresh(product)
    assert product.status == "stale"

    queued = await redis_mock.redis.lrange(QueueName.SCRAPING, 0, -1)
    assert len(queued) == 1
