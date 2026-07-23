"""
Tests for POST /payments/refund.

P1 fix: the original successful transaction must be scoped to the specific
order being refunded (not "any successful transaction by this user, oldest
first"), and the refund amount must be capped at what's actually left to
refund on that order.
"""
from decimal import Decimal

import pytest

from sk_shared.models.order import Order
from sk_shared.models.payment import PaymentTransaction
from sk_shared.models.product import Merchant, Product
from src.models.payment_workflow import PaymentWorkflow
from src.state.payment_workflow import PaymentStatus
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


async def _seed_second_order(user_id: int) -> Order:
    """Seed a second order for the same user with a distinct merchant/product
    (seed_signed_order hardcodes a single merchant domain, so it can't be
    called twice in one test)."""
    async with TestingSessionLocal() as session:
        merchant = Merchant(name="Second Merchant", normalized_name="second-merchant", domain="second.example.com")
        session.add(merchant)
        await session.flush()
        prod = Product(merchant_id=merchant.id, name="Second Product", url="https://second.example.com/p/1", currency="PKR", cost_price=Decimal("5000"), sale_price=Decimal("5200"), in_stock=True)
        session.add(prod)
        await session.flush()
        order = Order(user_id=user_id, product_id=prod.id, status="contracts_signed", total_amount=Decimal("5200"), down_payment_amount=Decimal("1300"))
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def _seed_captured_payment(order, user_id, amount_pkr, idempotency_key, gateway_txn_id):
    """Seed a CAPTURED PaymentWorkflow + successful PaymentTransaction for an
    order, bypassing the down-payment API (its jazzcash confirm path currently
    hits an unrelated pre-existing bug: `payment.confirmed` is not registered
    in sk_shared.events._KNOWN_EVENTS)."""
    async with TestingSessionLocal() as session:
        workflow = PaymentWorkflow(
            order_id=order.id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            status=PaymentStatus.CAPTURED,
            gateway="jazzcash",
            gateway_session_id=gateway_txn_id,
            amount_pkr=Decimal(amount_pkr),
        )
        session.add(workflow)

        txn = PaymentTransaction(
            order_id=order.id,
            user_id=user_id,
            amount=Decimal(amount_pkr),
            currency="PKR",
            gateway="jazzcash",
            gateway_txn_id=gateway_txn_id,
            transaction_type="down_payment",
            status="success",
        )
        session.add(txn)
        await session.commit()
        await session.refresh(workflow)
        return workflow


async def test_refund_matches_transaction_for_the_requested_order_only(client, test_user, seed_signed_order):
    """Regression: a user with a successful payment on an older order must not
    have that older transaction picked as the refund target for a newer order."""
    user, token = test_user
    order_a, _ = await seed_signed_order(user.id)
    order_b = await _seed_second_order(user.id)

    await _seed_captured_payment(order_a, user.id, "1300.00", "refund-scope-a", "jc-txn-a")
    await _seed_captured_payment(order_b, user.id, "1300.00", "refund-scope-b", "jc-txn-b")

    resp = await client.post(
        "/api/v1/payments/refund",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order_b.id,
            "amount_pkr": "1300.00",
            "reason": "customer requested refund",
            "refund_reference": "refund-ref-order-b-001",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["order_id"] == order_b.id
    assert resp.json()["status"] == "settled"


async def test_refund_rejects_amount_exceeding_original_payment(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)
    await _seed_captured_payment(order, user.id, "1300.00", "refund-ceiling-001", "jc-txn-ceiling")

    resp = await client.post(
        "/api/v1/payments/refund",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order.id,
            "amount_pkr": "5000.00",  # Far more than the 1300 actually paid
            "reason": "customer requested refund",
            "refund_reference": "refund-ref-ceiling-001",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "REFUND_AMOUNT_EXCEEDS_AVAILABLE"


async def test_refund_rejects_amount_exceeding_remaining_after_prior_refund(client, test_user, seed_signed_order):
    """A first partial refund succeeds; a second refund that would push the
    total above the original payment must be rejected."""
    user, token = test_user
    order, _ = await seed_signed_order(user.id)
    await _seed_captured_payment(order, user.id, "1300.00", "refund-partial-001", "jc-txn-partial")

    first = await client.post(
        "/api/v1/payments/refund",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order.id,
            "amount_pkr": "800.00",
            "reason": "partial refund",
            "refund_reference": "refund-ref-partial-first",
        },
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/payments/refund",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order.id,
            "amount_pkr": "800.00",  # 800 + 800 = 1600 > 1300 paid
            "reason": "second partial refund",
            "refund_reference": "refund-ref-partial-second",
        },
    )
    assert second.status_code == 422
    assert second.json()["detail"] == "REFUND_AMOUNT_EXCEEDS_AVAILABLE"


async def test_refund_rejects_when_no_successful_transaction_for_order(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)
    # No payment made on this order at all.

    resp = await client.post(
        "/api/v1/payments/refund",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order.id,
            "amount_pkr": "100.00",
            "reason": "customer requested refund",
            "refund_reference": "refund-ref-no-txn",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "NO_SUCCESSFUL_TRANSACTION_FOUND"
