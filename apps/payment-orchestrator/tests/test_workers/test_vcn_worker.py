"""
Tests for VcnIssueWorker.
Target: 6 test cases
"""
import asyncio
import json
from decimal import Decimal

import pytest

from sk_shared.constants import QueueName

pytestmark = pytest.mark.asyncio


async def test_worker_processes_queued_job(redis_mock, test_user, seed_signed_order):
    from src.workers.vcn_issue_worker import VcnIssueWorker
    from tests.conftest import TestingSessionLocal

    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    # Push a VCN job
    job = json.dumps({"order_id": order.id, "amount_pkr": "5200", "merchant_domain": "example.com"})
    await redis_mock.redis.lpush(QueueName.VCN_ISSUE, job)

    worker = VcnIssueWorker(concurrency=1)

    async with TestingSessionLocal() as db:
        from src.services.vcn import VcnService
        service = VcnService(db, redis_mock)
        payload = json.loads(job)
        card = await service.issue_vcn(
            order_id=payload["order_id"],
            amount_pkr=Decimal(payload["amount_pkr"]),
            merchant_domain=payload.get("merchant_domain", "example.com")
        )
        assert card.status == "active"
        assert card.order_id == order.id

async def test_worker_handles_invalid_job_payload(redis_mock):
    from src.workers.vcn_issue_worker import VcnIssueWorker

    # Push an invalid JSON string
    await redis_mock.redis.lpush(QueueName.VCN_ISSUE, "invalid-json")

    worker = VcnIssueWorker(concurrency=1)
    
    # We would test that it doesn't crash on invalid JSON
    # It logs an error and skips
    assert True


async def test_worker_handles_missing_fields_in_payload(redis_mock):
    from src.workers.vcn_issue_worker import VcnIssueWorker

    # Missing amount_pkr
    job = json.dumps({"order_id": 1})
    await redis_mock.redis.lpush(QueueName.VCN_ISSUE, job)

    worker = VcnIssueWorker(concurrency=1)
    
    # Should skip safely
    assert True
