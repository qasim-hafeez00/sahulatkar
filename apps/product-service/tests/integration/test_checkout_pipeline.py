import pytest

from sk_shared.constants import QueueName


@pytest.mark.asyncio
async def test_integration_checkout_queue_api_flow(client, db_session, redis_mock):
    response = await client.post(
        "/api/v1/products/agent/queue-job",
        json={"order_id": 1201, "vcn_id": 2201},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"

    queued_items = await redis_mock.redis.lrange(QueueName.CHECKOUT, 0, -1)
    assert len(queued_items) == 1
