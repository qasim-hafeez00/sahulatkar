from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import select

from sk_shared.models.product import ScrapingJob


@pytest.mark.asyncio
async def test_job_status_not_found(client):
    res = await client.get("/api/v1/products/jobs/00000000-0000-0000-0000-000000000001")
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
