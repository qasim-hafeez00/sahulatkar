from __future__ import annotations

from types import MethodType

import pytest

from src.billing.billing_sweep import BillingSweepService


class _FakeRawRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True


class _FakeRedisClient:
    def __init__(self) -> None:
        self.redis = _FakeRawRedis()

    async def get(self, key: str):
        return self.redis.store.get(key)

    async def delete(self, key: str):
        self.redis.store.pop(key, None)


@pytest.mark.asyncio
async def test_billing_sweep_skips_when_lock_already_held(db_session):
    fake_redis = _FakeRedisClient()
    await fake_redis.redis.set(BillingSweepService.LOCK_KEY, "other-owner", nx=True)

    service = BillingSweepService(db_session, redis=fake_redis)
    stats = await service.execute_sweep()

    assert stats == {"total": 0, "success": 0, "failed": 0, "already_paid": 0, "newly_overdue": 0, "late_fees_applied": 0}


@pytest.mark.asyncio
async def test_billing_sweep_releases_lock_after_run(db_session):
    fake_redis = _FakeRedisClient()
    service = BillingSweepService(db_session, redis=fake_redis)

    async def _empty_due_installments(self, as_of=None, limit=500):
        return []

    service.load_due_installments = MethodType(_empty_due_installments, service)

    stats = await service.execute_sweep()
    assert stats == {"total": 0, "success": 0, "failed": 0, "already_paid": 0, "newly_overdue": 0, "late_fees_applied": 0}
    assert BillingSweepService.LOCK_KEY not in fake_redis.redis.store
