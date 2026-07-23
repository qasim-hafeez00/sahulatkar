from __future__ import annotations

import pytest

from src.services.charity_service import CharityService


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
async def test_charity_disbursement_skips_when_lock_already_held(db_session):
    """P1: a concurrent disbursement run (e.g. an admin click racing a
    scheduled sweep) must not double-post the same allocations' GL entry —
    the second caller should back off instead of racing the first."""
    fake_redis = _FakeRedisClient()
    await fake_redis.redis.set(CharityService.LOCK_KEY, "other-owner", nx=True)

    service = CharityService(db_session, redis=fake_redis)
    result = await service.process_charity_allocation()

    assert result["status"] == "locked"
    assert result["disbursed_count"] == 0
    # The lock holder that wasn't us must be left alone.
    assert fake_redis.redis.store[CharityService.LOCK_KEY] == "other-owner"


@pytest.mark.asyncio
async def test_charity_disbursement_releases_lock_after_run(db_session):
    fake_redis = _FakeRedisClient()
    service = CharityService(db_session, redis=fake_redis)

    result = await service.process_charity_allocation()

    assert result["status"] == "no_pending"
    assert CharityService.LOCK_KEY not in fake_redis.redis.store


@pytest.mark.asyncio
async def test_charity_disbursement_requires_redis_for_locking(db_session):
    service = CharityService(db_session, redis=None)

    with pytest.raises(RuntimeError, match="Redis client is mandatory"):
        await service.process_charity_allocation()
