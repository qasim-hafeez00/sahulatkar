"""
Tests for GET /admin/payments/transactions — specifically the order_id link.

Regression coverage for the TODO previously at admin.py:72
(`order_id=None,  # TODO: Derive from loan.order_id if needed`).
PaymentTransaction rows are created (src/api/v1/payments.py) with loan_id/
installment_id only — order_id is never set directly on the row — so the
admin transaction list must derive it via a join to Loan instead of always
returning None.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sk_shared.models.auth import AdminUser
from sk_shared.models.payment import PaymentTransaction
from sk_shared.security import create_access_token, get_password_hash

pytestmark = pytest.mark.asyncio

from datetime import timedelta

from src.config import settings


async def _seed_admin(db_session, role: str) -> int:
    admin = AdminUser(
        email=f"{role}-txn@sahulatkar.pk",
        password_hash=get_password_hash("irrelevant"),
        mfa_enabled=False,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin.id


def _admin_token(admin_id: int, role: str) -> str:
    return create_access_token(
        {"admin_id": admin_id, "role": role, "token_type": "admin"},
        settings.JWT_PRIVATE_KEY,
        timedelta(seconds=900),
    )


async def test_list_transactions_derives_order_id_from_loan(client, db_session, seed_order_with_loan):
    """A transaction linked only via loan_id must still surface the originating order_id."""
    order, loan = await seed_order_with_loan(user_id=42)

    txn = PaymentTransaction(
        loan_id=loan.id,
        user_id=42,
        amount=Decimal("975.00"),
        currency="PKR",
        gateway="safepay",
        gateway_txn_id="TXN-ORDER-LINK-1",
        status="success",
    )
    db_session.add(txn)
    await db_session.commit()

    admin_id = await _seed_admin(db_session, "finance")
    token = _admin_token(admin_id, "finance")

    resp = await client.get(
        "/api/v1/admin/payments/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    matching = [item for item in body["items"] if item["gateway_txn_id"] == "TXN-ORDER-LINK-1"]
    assert len(matching) == 1
    assert matching[0]["order_id"] == order.id


async def test_list_transactions_order_id_null_when_no_loan(client, db_session):
    """A transaction with no loan_id at all (e.g. orphaned/system txn) must report order_id=None, not error."""
    txn = PaymentTransaction(
        loan_id=None,
        user_id=99,
        amount=Decimal("100.00"),
        currency="PKR",
        gateway="stripe",
        gateway_txn_id="TXN-NO-LOAN-1",
        status="success",
    )
    db_session.add(txn)
    await db_session.commit()

    admin_id = await _seed_admin(db_session, "support")
    token = _admin_token(admin_id, "support")

    resp = await client.get(
        "/api/v1/admin/payments/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    matching = [item for item in body["items"] if item["gateway_txn_id"] == "TXN-NO-LOAN-1"]
    assert len(matching) == 1
    assert matching[0]["order_id"] is None


async def test_list_transactions_direct_order_id_wins_over_loan_order_id(client, db_session, seed_order_with_loan):
    """If a row ever does have order_id set directly, it must take priority over the joined loan.order_id."""
    order, loan = await seed_order_with_loan(user_id=7)

    # Simulate a different, unrelated order set directly on the row —
    # direct order_id should win even though loan_id points elsewhere.
    from sk_shared.models.order import Order
    from sk_shared.models.product import Merchant, Product

    merchant = Merchant(name="Other Merchant", normalized_name="other-merchant", domain="other.com")
    db_session.add(merchant)
    await db_session.flush()
    prod = Product(merchant_id=merchant.id, name="Other Product", url="https://other.com/p/1", currency="PKR", cost_price=Decimal("1000"), sale_price=Decimal("1200"), in_stock=True)
    db_session.add(prod)
    await db_session.flush()
    other_order = Order(user_id=7, product_id=prod.id, status="down_payment_received", total_amount=Decimal("1200"), down_payment_amount=Decimal("300"))
    db_session.add(other_order)
    await db_session.flush()

    txn = PaymentTransaction(
        order_id=other_order.id,
        loan_id=loan.id,
        user_id=7,
        amount=Decimal("300.00"),
        currency="PKR",
        gateway="jazzcash",
        gateway_txn_id="TXN-DIRECT-ORDER-1",
        status="success",
    )
    db_session.add(txn)
    await db_session.commit()

    admin_id = await _seed_admin(db_session, "finance")
    token = _admin_token(admin_id, "finance")

    resp = await client.get(
        "/api/v1/admin/payments/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    matching = [item for item in body["items"] if item["gateway_txn_id"] == "TXN-DIRECT-ORDER-1"]
    assert len(matching) == 1
    assert matching[0]["order_id"] == other_order.id
    assert matching[0]["order_id"] != order.id
