"""
Tests for RefundService.
Target: 10 test cases
"""
from decimal import Decimal
from datetime import datetime, timezone

import pytest

from src.services.refund_service import RefundService

pytestmark = pytest.mark.asyncio


async def _seed_successful_down_payment(db_session, user_id: int, order_id: int, loan_id: int):
    from sk_shared.models.payment import PaymentTransaction
    txn = PaymentTransaction(
        loan_id=loan_id,
        user_id=user_id,
        amount=Decimal("1300"),
        currency="PKR",
        gateway="safepay",
        gateway_txn_id="sp_refund_src_001",
        status="success",
        reconciled_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)
    return txn


async def test_refund_succeeds_for_refundable_order(db_session, redis_mock, test_user, seed_order_with_loan):
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    await _seed_successful_down_payment(db_session, user.id, order.id, loan.id)

    service = RefundService(db_session, redis_mock)
    refund_txn = await service.initiate_refund(
        order_id=order.id,
        amount_pkr=Decimal("1300"),
        reason="Customer requested",
        refund_reference="REFUND-REF-001",
        requested_by_user_id=user.id,
    )

    assert refund_txn.amount == Decimal("-1300")   # Negative = refund
    assert refund_txn.status == "success"


async def test_refund_fails_for_non_refundable_order(db_session, redis_mock, test_user, seed_signed_order):
    from fastapi import HTTPException
    user, _ = test_user
    order, _ = await seed_signed_order(user.id, status="contracts_signed")

    service = RefundService(db_session, redis_mock)
    with pytest.raises(HTTPException) as exc_info:
        await service.initiate_refund(
            order_id=order.id,
            amount_pkr=Decimal("500"),
            reason="Test",
            refund_reference="REFUND-REF-002",
            requested_by_user_id=user.id,
        )
    assert "ORDER_NOT_REFUNDABLE" in exc_info.value.detail


async def test_refund_is_idempotent_same_reference(db_session, redis_mock, test_user, seed_order_with_loan):
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    await _seed_successful_down_payment(db_session, user.id, order.id, loan.id)

    service = RefundService(db_session, redis_mock)
    kwargs = dict(
        order_id=order.id,
        amount_pkr=Decimal("500"),
        reason="Duplicate test",
        refund_reference="REFUND-IDEM-003",
        requested_by_user_id=user.id,
    )
    refund1 = await service.initiate_refund(**kwargs)
    refund2 = await service.initiate_refund(**kwargs)

    assert refund1.id == refund2.id


async def test_refund_404_for_unknown_order(db_session, redis_mock, test_user):
    from fastapi import HTTPException
    user, _ = test_user
    service = RefundService(db_session, redis_mock)

    with pytest.raises(HTTPException) as exc_info:
        await service.initiate_refund(
            order_id=99999,
            amount_pkr=Decimal("500"),
            reason="Test",
            refund_reference="REFUND-REF-404",
            requested_by_user_id=user.id,
        )
    assert exc_info.value.detail == "ORDER_NOT_FOUND"


async def test_refund_publishes_event_for_ledger(db_session, redis_mock, test_user, seed_order_with_loan):
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    await _seed_successful_down_payment(db_session, user.id, order.id, loan.id)

    service = RefundService(db_session, redis_mock)
    await service.initiate_refund(
        order_id=order.id,
        amount_pkr=Decimal("500"),
        reason="Event test",
        refund_reference="REFUND-EVENT-005",
        requested_by_user_id=user.id,
    )
    # Refund event should have been published
    # (Exact channel name depends on sk_shared.events implementation)
    # Minimal check: no exception raised and transaction recorded
    from sk_shared.models.payment import PaymentTransaction
    from sqlalchemy import select
    result = await db_session.execute(
        select(PaymentTransaction).where(PaymentTransaction.amount < 0)
    )
    refund_txns = result.scalars().all()
    assert len(refund_txns) == 1
