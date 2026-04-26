from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from sk_shared.models.payment import VirtualCard
from src.workers.vcn_expiry_worker import VcnExpiryWorker
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


async def _create_vcn(session, *, status: str, expires_delta_hours: int) -> VirtualCard:
    now = datetime.now(timezone.utc)
    card = VirtualCard(
        order_id=int(now.timestamp() * 1000) % 1_000_000_000,
        user_id=777,
        issuer="stripe",
        issuer_card_id=f"ic_test_{now.timestamp()}",
        masked_number="**** **** **** 4242",
        card_expiry=(now + timedelta(days=365)).date(),
        authorized_amount=Decimal("5200.00"),
        loaded_amount=Decimal("5200.00"),
        mcc_lock="retail",
        merchant_lock=None,
        charged_amount=Decimal("0.00"),
        is_used=False,
        status=status,
        issued_at=now,
        expires_at=now + timedelta(hours=expires_delta_hours),
        encrypted_pan=b"enc-pan",
        encrypted_cvv=b"enc-cvv",
    )
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return card


async def test_vcn_expiry_worker_marks_expired_and_calls_stripe(monkeypatch):
    import src.workers.vcn_expiry_worker as module

    monkeypatch.setattr(module, "SessionLocal", TestingSessionLocal)

    calls = []

    def _fake_cancel(self, issuer_card_id: str) -> bool:
        calls.append(issuer_card_id)
        return True

    monkeypatch.setattr("src.adapters.stripe_issuing.StripeIssuingAdapter.cancel_card", _fake_cancel)

    async with TestingSessionLocal() as db:
        card = await _create_vcn(db, status="active", expires_delta_hours=-2)

    worker = VcnExpiryWorker()
    await worker.sweep_expired_vcns()

    async with TestingSessionLocal() as db:
        c2 = await db.get(VirtualCard, card.id)
        assert c2.status == "expired"

    assert len(calls) == 1


async def test_vcn_expiry_worker_ignores_non_active(monkeypatch):
    import src.workers.vcn_expiry_worker as module

    monkeypatch.setattr(module, "SessionLocal", TestingSessionLocal)

    calls = []

    def _fake_cancel(self, issuer_card_id: str) -> bool:
        calls.append(issuer_card_id)
        return True

    monkeypatch.setattr("src.adapters.stripe_issuing.StripeIssuingAdapter.cancel_card", _fake_cancel)

    async with TestingSessionLocal() as db:
        card = await _create_vcn(db, status="voided", expires_delta_hours=-2)

    worker = VcnExpiryWorker()
    await worker.sweep_expired_vcns()

    async with TestingSessionLocal() as db:
        c2 = await db.get(VirtualCard, card.id)
        assert c2.status == "voided"

    assert len(calls) == 0


async def test_vcn_expiry_worker_ignores_not_yet_expired(monkeypatch):
    import src.workers.vcn_expiry_worker as module

    monkeypatch.setattr(module, "SessionLocal", TestingSessionLocal)

    calls = []

    def _fake_cancel(self, issuer_card_id: str) -> bool:
        calls.append(issuer_card_id)
        return True

    monkeypatch.setattr("src.adapters.stripe_issuing.StripeIssuingAdapter.cancel_card", _fake_cancel)

    async with TestingSessionLocal() as db:
        card = await _create_vcn(db, status="active", expires_delta_hours=2)

    worker = VcnExpiryWorker()
    await worker.sweep_expired_vcns()

    async with TestingSessionLocal() as db:
        c2 = await db.get(VirtualCard, card.id)
        assert c2.status == "active"

    assert len(calls) == 0


async def test_vcn_expiry_worker_stop_sets_flag_false():
    worker = VcnExpiryWorker()
    assert worker.is_running is True
    worker.stop()
    assert worker.is_running is False
