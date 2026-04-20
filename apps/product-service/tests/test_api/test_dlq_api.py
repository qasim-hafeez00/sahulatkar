import json

import pytest


@pytest.mark.asyncio
async def test_admin_dlq_reprocess_and_purge(client, redis_mock, service_header):
    await redis_mock.redis.lpush(
        "sk:queue:dlq:checkout",
        json.dumps({"execution_id": "exec-123", "dlq_error": "boom"}),
    )

    replay = await client.post(
        "/api/v1/admin/dlq/checkout/reprocess/0",
        headers=service_header,
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "requeued"
    assert replay.json()["item_id"] == "exec-123"

    await redis_mock.redis.lpush(
        "sk:queue:dlq:checkout",
        json.dumps({"execution_id": "exec-456", "dlq_error": "boom"}),
    )
    purge = await client.delete(
        "/api/v1/admin/dlq/checkout/purge",
        headers=service_header,
    )
    assert purge.status_code == 200
    assert purge.json()["purged"] == 1


@pytest.mark.asyncio
async def test_admin_dlq_rejects_unknown_queue(client, service_header):
    res = await client.post("/api/v1/admin/dlq/unknown/reprocess/0", headers=service_header)
    assert res.status_code == 400
    assert res.json()["detail"] == "INVALID_DLQ_QUEUE"