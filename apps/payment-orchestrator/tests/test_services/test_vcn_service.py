"""
Unit tests for VcnService business logic.
Ensures DDD compliance (no direct Loan mutations) and proper event emission.
"""
from decimal import Decimal
from dataclasses import asdict

import pytest
from sqlalchemy import select

from src.services.vcn import VcnService
from src.models.outbox import OutboxEvent
from sk_shared.events import EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED, EVENT_VCN_ISSUED

pytestmark = pytest.mark.asyncio


async def test_issue_vcn_success(db_session, redis_mock, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    service = VcnService(db_session, redis_mock)
    card = await service.issue_vcn(order_id=order.id, amount_pkr=Decimal("5200"))

    assert card.status == "active"
    assert card.masked_number.startswith("**** **** ****")
    assert card.encrypted_pan is not None
    assert card.encrypted_cvv is not None
    assert card.order_id == order.id

    # Verify outbox event for VCN issuance
    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_name == EVENT_VCN_ISSUED)
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].payload["payload"]["order_id"] == order.id


async def test_issue_vcn_blocks_without_signed_contract(db_session, redis_mock, test_user, seed_signed_order):
    from fastapi import HTTPException
    user, _ = test_user
    order, _ = await seed_signed_order(user.id, status="contracts_pending")

    service = VcnService(db_session, redis_mock)
    with pytest.raises(HTTPException) as exc_info:
        await service.issue_vcn(order_id=order.id, amount_pkr=Decimal("5200"))

    assert exc_info.value.detail == "MURABAHA_NOT_SIGNED"


async def test_issue_vcn_is_idempotent(db_session, redis_mock, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    service = VcnService(db_session, redis_mock)
    card1 = await service.issue_vcn(order_id=order.id, amount_pkr=Decimal("5200"))
    card2 = await service.issue_vcn(order_id=order.id, amount_pkr=Decimal("5200"))

    assert card1.id == card2.id


async def test_decrypt_vcn_returns_plaintext_pan(db_session, redis_mock, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    service = VcnService(db_session, redis_mock)
    await service.issue_vcn(order_id=order.id, amount_pkr=Decimal("5200"))

    decrypted = await service.decrypt_vcn(order.id)
    assert len(decrypted["pan"]) == 16
    assert decrypted["pan"].isdigit()
    assert len(decrypted["cvv"]) == 3
    assert decrypted["cvv"].isdigit()


async def test_decrypt_vcn_404_when_not_issued(db_session, redis_mock):
    from fastapi import HTTPException
    service = VcnService(db_session, redis_mock)
    with pytest.raises(HTTPException) as exc_info:
        await service.decrypt_vcn(99999)
    assert exc_info.value.detail == "VCN_NOT_FOUND"


async def test_confirm_down_payment_emits_outbox_event(db_session, redis_mock, test_user, seed_signed_order):
    """BV-01: confirm_down_payment MUST emit event via outbox instead of mutating Loan."""
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)
    
    service = VcnService(db_session, redis_mock)
    await service.confirm_down_payment(
        order_id=order.id,
        amount_pkr=Decimal("1300"),
        gateway_txn_id="txn_test_001",
    )
    await db_session.flush()

    # Verify outbox event
    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_name == EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED)
    )
    events = result.scalars().all()
    assert len(events) == 1
    payload = events[0].payload["payload"]
    assert payload["order_id"] == order.id
    assert payload["amount_pkr"] == "1300"
    assert payload["gateway_txn_id"] == "txn_test_001"


async def test_confirm_down_payment_is_idempotent_event_wise(db_session, redis_mock, test_user, seed_signed_order):
    """Verifies that calling confirm_down_payment multiple times is safe (emits multiple events which are deduped downstream)."""
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)
    
    service = VcnService(db_session, redis_mock)
    await service.confirm_down_payment(order_id=order.id, amount_pkr=Decimal("1300"), gateway_txn_id="txn_a")
    await service.confirm_down_payment(order_id=order.id, amount_pkr=Decimal("1300"), gateway_txn_id="txn_b")
    await db_session.flush()

    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_name == EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED)
    )
    events = result.scalars().all()
    assert len(events) == 2


async def test_vcn_pan_starts_with_4(db_session, redis_mock, test_user, seed_signed_order):
    """VCN PAN should start with '4' (Visa BIN range for internal test cards)."""
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    service = VcnService(db_session, redis_mock)
    await service.issue_vcn(order_id=order.id, amount_pkr=Decimal("5200"))
    decrypted = await service.decrypt_vcn(order.id)
    assert decrypted["pan"][0] == "4"


async def test_queue_issue_pushes_to_outbox(db_session, redis_mock, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    service = VcnService(db_session, redis_mock)
    await service.queue_issue(
        order_id=order.id,
        amount_pkr=Decimal("5200"),
        merchant_domain="example.com",
    )
    await db_session.flush()

    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_name == "vcn.issue")
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].payload["order_id"] == order.id
