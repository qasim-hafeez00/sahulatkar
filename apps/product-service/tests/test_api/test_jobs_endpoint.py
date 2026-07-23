from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import select

from sk_shared.models.product import ScrapingJob


@pytest.mark.asyncio
async def test_job_status_not_found(client, user_header):
    res = await client.get(
        "/api/v1/products/jobs/00000000-0000-0000-0000-000000000001",
        headers=user_header,
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "JOB_NOT_FOUND"


@pytest.mark.asyncio
async def test_job_status_requires_authentication(client):
    res = await client.get("/api/v1/products/jobs/00000000-0000-0000-0000-000000000001")
    # No internal-service-token at all: Zero-Trust identity resolution
    # rejects this before we even get to the ownership check.
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_job_status_requires_user_id(client, service_header):
    res = await client.get(
        "/api/v1/products/jobs/00000000-0000-0000-0000-000000000001",
        headers=service_header,
    )
    # Valid service token but no x-user-id: there's no authenticated user to
    # own this poll request.
    assert res.status_code == 401
    assert res.json()["detail"] == "USER_ID_REQUIRED"


@pytest.mark.asyncio
async def test_job_status_returns_status_for_owning_user(client, db_session, make_scraping_job, user_header):
    job = await make_scraping_job(db_session, user_id=101)
    await db_session.commit()

    res = await client.get(f"/api/v1/products/jobs/{job.uuid}", headers=user_header)
    assert res.status_code == 200
    body = res.json()
    assert body["job_id"] == str(job.uuid)
    assert body["status"] == job.status


@pytest.mark.asyncio
async def test_job_status_blocks_other_users_job(client, db_session, make_scraping_job, user_header):
    """A user must not be able to poll another user's job. This should
    return 404 (not 403) so the caller can't distinguish "not found" from
    "exists but isn't yours" and enumerate other users' job ids.
    """
    job = await make_scraping_job(db_session, user_id=202)
    await db_session.commit()

    res = await client.get(f"/api/v1/products/jobs/{job.uuid}", headers=user_header)
    assert res.status_code == 404
    assert res.json()["detail"] == "JOB_NOT_FOUND"


@pytest.mark.asyncio
async def test_job_status_blocks_ownerless_job(client, db_session, make_scraping_job, user_header):
    """A job with no owner (e.g. created by an internal/service flow) must
    not be pollable by an arbitrary authenticated user either.
    """
    job = await make_scraping_job(db_session, user_id=None)
    await db_session.commit()

    res = await client.get(f"/api/v1/products/jobs/{job.uuid}", headers=user_header)
    assert res.status_code == 404
    assert res.json()["detail"] == "JOB_NOT_FOUND"


@pytest.mark.asyncio
async def test_refresh_enqueues_scraping_job_with_uuid_payload(client, db_session, make_product, redis_mock, service_header):
    product = await make_product(db_session)
    await db_session.commit()

    res = await client.post(
        f"/api/v1/products/{product.uuid}/refresh",
        headers=service_header,
        json={"reason": "stale_price"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "queued"

    queued = await redis_mock.redis.lindex("sk:queue:scraping", 0)
    assert queued is not None
    assert str(body["job_id"]) in queued.decode("utf-8")

    job = await db_session.scalar(select(ScrapingJob).where(ScrapingJob.uuid == UUID(body["job_id"])))
    assert job is not None


@pytest.mark.asyncio
async def test_refresh_reuses_existing_active_job(client, db_session, make_product, service_header):
    product = await make_product(db_session)
    await db_session.flush()
    existing = ScrapingJob(
        product_id=product.id,
        input_url=product.url,
        canonical_url=product.canonical_url,
        platform_detected=product.platform,
        status="running",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(existing)
    await db_session.commit()

    res = await client.post(
        f"/api/v1/products/{product.uuid}/refresh",
        headers=service_header,
        json={"reason": "manual_refresh"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "queued"
    assert payload["job_id"] == str(existing.uuid)
