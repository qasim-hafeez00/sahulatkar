from datetime import datetime, timezone

import pytest

from sk_shared.models.checkout import PurchaseExecution


@pytest.mark.asyncio
async def test_cancel_checkout_job_requires_service_token(client):
    res = await client.post("/api/v1/products/agent/job/00000000-0000-0000-0000-000000000001/cancel")
    assert res.status_code in {401, 403}


@pytest.mark.asyncio
async def test_stream_job_status_emits_done(client, db_session, make_execution):
    execution = await make_execution(
        db_session,
        status="succeeded",
        step_reached="receipt",
        completed_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    res = await client.get(f"/api/v1/products/agent/job/{execution.uuid}/stream")
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")
    text = res.text
    assert "\"done\": true" in text


@pytest.mark.asyncio
async def test_cancel_checkout_job_not_found(client, service_header):
    res = await client.post(
        "/api/v1/products/agent/job/00000000-0000-0000-0000-000000000001/cancel",
        headers=service_header,
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "JOB_NOT_FOUND"
