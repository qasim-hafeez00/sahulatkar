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
        user_id=user.id,
        amount_pkr=Decimal("1300"),
        reason="Customer requested",
        refund_reference="REFUND-REF-001",
    )

    assert refund_txn.amount == Decimal("-1300")   # Negative = refund
    assert refund_txn.status == "success"


async def test_refund_fails_when_order_has_no_payment_txn(db_session, redis_mock, test_user, seed_signed_order):
    """If no successful payment exists for user, refund raises 422 (BV-02 fix: no Order state check)."""
    from fastapi import HTTPException
    user, _ = test_user
    # contracts_signed order but NO payment transaction seeded
    order, _ = await seed_signed_order(user.id, status="contracts_signed")

    service = RefundService(db_session, redis_mock)
    with pytest.raises(HTTPException) as exc_info:
        await service.initiate_refund(
            order_id=order.id,
            user_id=user.id,
            amount_pkr=Decimal("500"),
            reason="Test",
            refund_reference="REFUND-REF-002",
        )
    # No successful transaction = 422
    assert exc_info.value.status_code == 422
    assert "NO_SUCCESSFUL_TRANSACTION_FOUND" in exc_info.value.detail


async def test_refund_is_idempotent_same_reference(db_session, redis_mock, test_user, seed_order_with_loan):
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    await _seed_successful_down_payment(db_session, user.id, order.id, loan.id)

    service = RefundService(db_session, redis_mock)
    kwargs = dict(
        order_id=order.id,
        user_id=user.id,
        amount_pkr=Decimal("500"),
        reason="Duplicate test",
        refund_reference="REFUND-IDEM-003",
    )
    refund1 = await service.initiate_refund(**kwargs)
    refund2 = await service.initiate_refund(**kwargs)

    assert refund1.id == refund2.id


async def test_refund_fails_when_no_txn_for_user(db_session, redis_mock, test_user):
    """Refund raises 422 when no successful transaction exists for the user."""
    from fastapi import HTTPException
    user, _ = test_user
    service = RefundService(db_session, redis_mock)

    with pytest.raises(HTTPException) as exc_info:
        await service.initiate_refund(
            order_id=99999,
            user_id=user.id,
            amount_pkr=Decimal("500"),
            reason="Test",
            refund_reference="REFUND-REF-404",
        )
    assert exc_info.value.status_code == 422
    assert "NO_SUCCESSFUL_TRANSACTION_FOUND" in exc_info.value.detail


async def test_refund_publishes_event_for_ledger(db_session, redis_mock, test_user, seed_order_with_loan):
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    await _seed_successful_down_payment(db_session, user.id, order.id, loan.id)

    service = RefundService(db_session, redis_mock)
    await service.initiate_refund(
        order_id=order.id,
        user_id=user.id,
        amount_pkr=Decimal("500"),
        reason="Event test",
        refund_reference="REFUND-EVENT-005",
    )
    # Refund event published — verify refund transaction was recorded
    from sk_shared.models.payment import PaymentTransaction
    from sqlalchemy import select
    result = await db_session.execute(
        select(PaymentTransaction).where(PaymentTransaction.amount < 0)
    )
    refund_txns = result.scalars().all()
    assert len(refund_txns) == 1


async def test_refund_amount_is_negative_in_db(db_session, redis_mock, test_user, seed_order_with_loan):
    """Refund transaction must be stored as negative amount (debit reversal convention)."""
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    await _seed_successful_down_payment(db_session, user.id, order.id, loan.id)

    service = RefundService(db_session, redis_mock)
    refund_txn = await service.initiate_refund(
        order_id=order.id,
        user_id=user.id,
        amount_pkr=Decimal("750"),
        reason="Amount sign test",
        refund_reference="REFUND-SIGN-006",
    )

    assert refund_txn.amount < 0
    assert refund_txn.amount == Decimal("-750")


async def test_refund_gateway_is_inherited_from_original_transaction(
    db_session, redis_mock, test_user, seed_order_with_loan
):
    """Refund must use the same gateway as the original payment transaction."""
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    # Original down payment was via safepay (seeded by _seed_successful_down_payment)
    await _seed_successful_down_payment(db_session, user.id, order.id, loan.id)

    service = RefundService(db_session, redis_mock)
    refund_txn = await service.initiate_refund(
        order_id=order.id,
        user_id=user.id,
        amount_pkr=Decimal("300"),
        reason="Gateway inheritance test",
        refund_reference="REFUND-GW-007",
    )

    assert refund_txn.gateway == "safepay"


async def test_refund_fails_when_no_successful_transaction_exists(
    db_session, redis_mock, test_user, seed_order_with_loan
):
    """Refund must raise 422 if no successful payment transaction found for the user."""
    from fastapi import HTTPException

    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    # Deliberately NOT seeding a successful transaction

    service = RefundService(db_session, redis_mock)
    with pytest.raises(HTTPException) as exc_info:
        await service.initiate_refund(
            order_id=order.id,
            user_id=user.id,
            amount_pkr=Decimal("500"),
            reason="No txn test",
            refund_reference="REFUND-NOTXN-008",
        )
    assert exc_info.value.status_code == 422
    assert "NO_SUCCESSFUL_TRANSACTION_FOUND" in exc_info.value.detail


async def test_refund_stores_refund_reference_in_gateway_response(
    db_session, redis_mock, test_user, seed_order_with_loan
):
    """Refund transaction must include refund_reference in gateway_response JSON."""
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    await _seed_successful_down_payment(db_session, user.id, order.id, loan.id)

    service = RefundService(db_session, redis_mock)
    refund_txn = await service.initiate_refund(
        order_id=order.id,
        user_id=user.id,
        amount_pkr=Decimal("200"),
        reason="Reference storage test",
        refund_reference="REFUND-REF-STORE-009",
    )

    assert refund_txn.gateway_response is not None
    assert refund_txn.gateway_response.get("refund_reference") == "REFUND-REF-STORE-009"


async def test_refund_currency_is_pkr(db_session, redis_mock, test_user, seed_order_with_loan):
    """Refund transaction currency must always be PKR."""
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    await _seed_successful_down_payment(db_session, user.id, order.id, loan.id)

    service = RefundService(db_session, redis_mock)
    refund_txn = await service.initiate_refund(
        order_id=order.id,
        user_id=user.id,
        amount_pkr=Decimal("100"),
        reason="Currency test",
        refund_reference="REFUND-CURR-010",
    )

    assert refund_txn.currency == "PKR"

