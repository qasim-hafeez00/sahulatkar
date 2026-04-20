import json

import pytest

from src.middleware.metrics import DLQ_DEPTH
from src.services.dlq_service import DLQService
from src.workers.dlq_worker import DLQMonitorWorker


@pytest.mark.asyncio
async def test_dlq_service_stats_list_reprocess_and_purge(redis_mock):
    service = DLQService(redis_mock)

    entry = {"execution_id": "exec-1", "dlq_error": "boom"}
    await redis_mock.redis.lpush("sk:queue:dlq:checkout", json.dumps(entry))

    stats = await service.get_stats()
    assert stats["checkout"] == 1
    assert stats["scraping"] == 0

    items = await service.list_entries("checkout")
    assert len(items) == 1
    assert items[0]["execution_id"] == "exec-1"

    item_id = await service.reprocess("checkout", 0)
    assert item_id == "exec-1"
    assert await redis_mock.redis.llen("sk:queue:dlq:checkout") == 0
    assert await redis_mock.redis.lindex("sk:queue:checkout", 0) is not None

    await redis_mock.redis.lpush("sk:queue:dlq:checkout", json.dumps(entry))
    purged = await service.purge("checkout")
    assert purged == 1
    assert await redis_mock.redis.llen("sk:queue:dlq:checkout") == 0


@pytest.mark.asyncio
async def test_dlq_worker_updates_metric(redis_mock):
    worker = DLQMonitorWorker(redis_mock, interval_seconds=0)

    for _ in range(51):
        await redis_mock.redis.lpush("sk:queue:dlq:checkout", json.dumps({"execution_id": "exec-1"}))

    stats = await worker._check_and_alert()
    assert stats["checkout"] == 51
    assert DLQ_DEPTH.labels(queue="checkout")._value.get() == 51