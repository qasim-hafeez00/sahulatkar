import pytest

from src.services.product_cache_service import ProductCacheService


@pytest.mark.asyncio
async def test_set_and_get_upo_roundtrip(redis_mock):
    svc = ProductCacheService()
    payload = {"product_id": "abc", "meta": {"title": "Demo"}}
    await svc.set_upo(redis_mock, "abc", payload)
    got = await svc.get_upo(redis_mock, "abc")
    assert got == payload


@pytest.mark.asyncio
async def test_invalidate_removes_keys(redis_mock):
    svc = ProductCacheService()
    await svc.set_by_url(redis_mock, "https://example.com/p/1", "uuid-1")
    await svc.set_upo(redis_mock, "uuid-1", {"ok": True})

    await svc.invalidate(redis_mock, "uuid-1", "https://example.com/p/1")
    assert await svc.get_upo(redis_mock, "uuid-1") is None


@pytest.mark.asyncio
async def test_job_status_roundtrip(redis_mock):
    svc = ProductCacheService()
    await svc.set_job_status(redis_mock, "job-x", "queued")
    assert await svc.get_job_status(redis_mock, "job-x") == "queued"
