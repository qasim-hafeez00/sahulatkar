import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue
from sk_shared.constants import QueueName
from src.workers.vcn_verification_worker import VcnVerificationWorker

class _SingleSessionFactory:
    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False

@pytest.mark.asyncio
async def test_vcn_verification_worker_success(monkeypatch, db_session, redis_mock):
    # Setup - execution matches decoppled pattern
    execution = PurchaseExecution(
        order_id=1,
        vcn_id=10,
        status="pending_verification",
        step_reached="pending_verification",
        queued_at=datetime.now(timezone.utc)
    )
    db_session.add(execution)
    await db_session.commit()

    payload = {
        "execution_id": str(execution.uuid),
        "vcn_id": 10,
        "order_id": 1
    }

    worker = VcnVerificationWorker(redis_mock)

    # Mock VcnVerifier to return True (simulating webhook arrival)
    async def mock_verify_charge(*args, **kwargs):
        return True

    monkeypatch.setattr("src.workers.vcn_verification_worker.SessionLocal", _SingleSessionFactory(db_session))
    monkeypatch.setattr("src.services.checkout.vcn_verifier.VcnVerifier.verify_charge", mock_verify_charge)

    # Process
    await worker._process_job(payload)

    # Verify
    await db_session.refresh(execution)
    assert execution.status == "succeeded"
    assert execution.step_reached == "order_confirmed"
    
    # Verify success event published
    events = await redis_mock.redis.lrange("sk:queue:events:purchase_confirmed", 0, -1)
    # The channel is dynamically built, but redis_mock might capture it if it's subscribed
    # Actually redis_mock.publish is what's used.
    # We can check if publish was called if we mock it further, but usually redis_mock tracks publishes.

@pytest.mark.asyncio
async def test_vcn_verification_worker_timeout_escalates_hitl(monkeypatch, db_session, redis_mock):
    execution = PurchaseExecution(
        order_id=2,
        vcn_id=20,
        status="pending_verification",
        step_reached="pending_verification",
        queued_at=datetime.now(timezone.utc)
    )
    db_session.add(execution)
    await db_session.commit()

    payload = {
        "execution_id": str(execution.uuid),
        "vcn_id": 20,
        "order_id": 2
    }

    worker = VcnVerificationWorker(redis_mock)

    # Mock VcnVerifier to return False (simulating timeout)
    async def mock_verify_charge(*args, **kwargs):
        return False

    monkeypatch.setattr("src.workers.vcn_verification_worker.SessionLocal", _SingleSessionFactory(db_session))
    monkeypatch.setattr("src.services.checkout.vcn_verifier.VcnVerifier.verify_charge", mock_verify_charge)
    monkeypatch.setattr("src.workers.vcn_verification_worker.settings.FEATURE_HITL_ESCALATION", True)

    # Process
    await worker._process_job(payload)

    # Verify
    await db_session.refresh(execution)
    assert execution.status == "hitl_escalated"
    
    hitl = await db_session.scalar(select(HitlQueue).where(HitlQueue.execution_id == execution.id))
    assert hitl is not None
    assert "timed out" in hitl.failure_reason
