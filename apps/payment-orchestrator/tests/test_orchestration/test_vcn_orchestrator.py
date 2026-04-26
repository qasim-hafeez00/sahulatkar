from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from sk_shared.models.payment import VirtualCard
from src.models.outbox import OutboxEvent
from src.orchestration.vcn_orchestrator import VcnOrchestrator

pytestmark = pytest.mark.asyncio


async def _make_card(db_session) -> VirtualCard:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    card = VirtualCard(
        order_id=int(now.timestamp() * 1000) % 1_000_000_000,
        user_id=777,
        issuer="stripe",
        issuer_card_id=f"ic_orch_{now.timestamp()}",
        masked_number="**** **** **** 4242",
        card_expiry=(now + timedelta(days=365)).date(),
        authorized_amount=Decimal("5200.00"),
        loaded_amount=Decimal("5200.00"),
        mcc_lock="retail",
        merchant_lock=None,
        charged_amount=Decimal("0.00"),
        is_used=False,
        status="active",
        issued_at=now,
        expires_at=now + timedelta(hours=24),
        encrypted_pan=b"enc-pan",
        encrypted_cvv=b"enc-cvv",
    )
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


async def test_handle_stripe_transaction_created_queues_vcn_charged(db_session):
    card = await _make_card(db_session)
    orchestrator = VcnOrchestrator(db_session)

    await orchestrator.handle_stripe_event(
        "issuing_transaction.created",
        {"card": card.issuer_card_id, "amount": 1234, "id": "itx_1"},
    )
    await db_session.commit()
    await db_session.refresh(card)

    assert card.is_used is True
    assert card.charged_amount == Decimal("0.00")

    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_name == "vcn.charged")
    )
    events = result.scalars().all()
    assert len(events) == 1


async def test_handle_stripe_authorization_request_approves(db_session):
    card = await _make_card(db_session)
    orchestrator = VcnOrchestrator(db_session)

    import stripe as stripe_module
    from unittest.mock import MagicMock, AsyncMock

    mock_auth = MagicMock()
    approve_fn = MagicMock(return_value=None)
    decline_fn = MagicMock(return_value=None)
    mock_auth.approve = approve_fn
    mock_auth.decline = decline_fn

    original_auth = stripe_module.issuing.Authorization
    stripe_module.issuing.Authorization = mock_auth
    try:
        await orchestrator.handle_stripe_event(
            "issuing_authorization.request",
            {"card": card.issuer_card_id, "id": "iauth_1", "pending_request": {"amount": 10}},
        )
    finally:
        stripe_module.issuing.Authorization = original_auth

    approve_fn.assert_called_once()
    decline_fn.assert_not_called()


async def test_handle_stripe_authorization_request_declines_when_over_limit(db_session):
    card = await _make_card(db_session)
    orchestrator = VcnOrchestrator(db_session)

    import stripe as stripe_module
    from unittest.mock import MagicMock

    mock_auth = MagicMock()
    approve_fn = MagicMock(return_value=None)
    decline_fn = MagicMock(return_value=None)
    mock_auth.approve = approve_fn
    mock_auth.decline = decline_fn

    original_auth = stripe_module.issuing.Authorization
    stripe_module.issuing.Authorization = mock_auth
    try:
        await orchestrator.handle_stripe_event(
            "issuing_authorization.request",
            {"card": card.issuer_card_id, "id": "iauth_2", "pending_request": {"amount": 9_999_999}},
        )
    finally:
        stripe_module.issuing.Authorization = original_auth

    approve_fn.assert_not_called()
    decline_fn.assert_called_once()
