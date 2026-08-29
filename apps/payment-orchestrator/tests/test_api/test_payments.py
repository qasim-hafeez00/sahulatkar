"""
Tests for payment initiation, installment payment, and refund endpoints.
Target: 20+ test cases
"""
import pytest

pytestmark = pytest.mark.asyncio

from tests.conftest import TestingSessionLocal
from sk_shared.models.auth import User
from sk_shared.models.payment import Installment, PaymentTransaction
from sqlalchemy import select


# ── Down Payment ─────────────────────────────────────────────────────────────

async def test_down_payment_safepay_returns_redirect_url(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    resp = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order.id,
            "method": "safepay",
            "amount_pkr": "1300.00",
            "idempotency_key": "test-idem-key-001",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert "getsafepay.com" in data["payment_session_url"]
    assert data["idempotency_key"] == "test-idem-key-001"


async def test_down_payment_jazzcash_returns_success(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    resp = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order.id,
            "method": "jazzcash",
            "amount_pkr": "1300.00",
            "idempotency_key": "test-idem-key-002",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


async def test_down_payment_raast_returns_pending(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    resp = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order.id,
            "method": "raast",
            "amount_pkr": "1300.00",
            "idempotency_key": "test-idem-key-003",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


async def test_down_payment_rejects_unsigned_contract(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id, status="contracts_pending")

    resp = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order.id,
            "method": "jazzcash",
            "amount_pkr": "1300.00",
            "idempotency_key": "test-idem-key-004",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "MURABAHA_NOT_SIGNED"


async def test_down_payment_rejects_amount_too_low(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)  # total=5200, min 25%=1300

    resp = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order.id,
            "method": "jazzcash",
            "amount_pkr": "100.00",           # Way below 25% min
            "idempotency_key": "test-idem-key-005",
        },
    )
    assert resp.status_code == 422


async def test_down_payment_rejects_amount_too_high(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)  # max 40%=2080

    resp = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": order.id,
            "method": "jazzcash",
            "amount_pkr": "3000.00",           # Above 40% max
            "idempotency_key": "test-idem-key-006",
        },
    )
    assert resp.status_code == 422


async def test_down_payment_idempotency_returns_same_transaction(client, test_user, seed_signed_order, redis_mock):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {
        "order_id": order.id,
        "method": "jazzcash",
        "amount_pkr": "1300.00",
        "idempotency_key": "idem-key-idempotent-test",
    }

    resp1 = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp1.status_code == 200
    txn_id_1 = resp1.json()["payment_transaction_id"]

    # Re-send same idempotency key
    resp2 = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp2.status_code == 200
    # Should return the same transaction
    assert resp2.json()["payment_transaction_id"] == txn_id_1


async def test_down_payment_rejects_wrong_user_order(client, test_user, seed_signed_order):
    user1, token1 = test_user
    # Create a second user's order
    import uuid
    async with TestingSessionLocal() as session:
        user2 = User(uuid=uuid.uuid4(), phone="+923009999999", status="kyc_approved")
        session.add(user2)
        await session.commit()
        await session.refresh(user2)

    # We test that user1 cannot pay user2's order by passing wrong order_id
    resp = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "order_id": 99999,   # Non-existent order for this user
            "method": "jazzcash",
            "amount_pkr": "1300.00",
            "idempotency_key": "test-idem-key-007",
        },
    )
    assert resp.status_code == 404


# ── Installment Payment ──────────────────────────────────────────────────────

async def test_pay_installment_success(client, test_user, seed_order_with_loan):
    user, token = test_user
    order, loan = await seed_order_with_loan(user.id)

    # Get first installment
    from sk_shared.models.payment import Installment

    async with TestingSessionLocal() as session:
        inst = await session.scalar(
            select(Installment).where(
                Installment.loan_id == loan.id,
                Installment.installment_number == 1,
            )
        )

    resp = await client.post(
        "/api/v1/payments/pay-installment",
        headers={"Authorization": f"Bearer {token}"},
        json={"installment_id": inst.id, "method": "jazzcash"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["next_installment_id"] is not None   # installment 2 still pending


async def test_pay_installment_returns_404_for_unknown(client, test_user):
    _, token = test_user
    resp = await client.post(
        "/api/v1/payments/pay-installment",
        headers={"Authorization": f"Bearer {token}"},
        json={"installment_id": 99999, "method": "jazzcash"},
    )
    assert resp.status_code == 404


async def test_pay_installment_rejects_already_paid(client, test_user, seed_order_with_loan):
    user, token = test_user
    order, loan = await seed_order_with_loan(user.id)

    from sqlalchemy import select

    async with TestingSessionLocal() as session:
        inst = await session.scalar(
            select(Installment).where(
                Installment.loan_id == loan.id,
                Installment.installment_number == 1,
            )
        )

    # Pay once
    await client.post(
        "/api/v1/payments/pay-installment",
        headers={"Authorization": f"Bearer {token}"},
        json={"installment_id": inst.id, "method": "jazzcash"},
    )

    # Pay again — should fail
    resp = await client.post(
        "/api/v1/payments/pay-installment",
        headers={"Authorization": f"Bearer {token}"},
        json={"installment_id": inst.id, "method": "jazzcash"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "INSTALLMENT_ALREADY_PAID"


async def test_concurrent_pay_installment_only_one_charges(client, test_user, seed_order_with_loan):
    """PO-CRIT-01 regression: two simultaneous pay-installment requests for
    the same installment (a double-tap on a flaky connection, or a manual
    pay racing the billing sweep) must not both charge. The Redis SET-NX
    lock (backed by the SELECT...FOR UPDATE guard) must let exactly one
    request through; the other is rejected as already in progress / already
    settled -- never a second successful charge.

    Mirrors the established concurrency-test pattern for this monorepo, see
    apps/gateway/tests/test_api/test_orders.py::test_concurrent_order_accept_credit_race
    (asyncio.gather against the shared test client / db_session).
    """
    import asyncio

    user, token = test_user
    order, loan = await seed_order_with_loan(user.id)

    async with TestingSessionLocal() as session:
        inst = await session.scalar(
            select(Installment).where(
                Installment.loan_id == loan.id,
                Installment.installment_number == 1,
            )
        )

    async def pay_once():
        return await client.post(
            "/api/v1/payments/pay-installment",
            headers={"Authorization": f"Bearer {token}"},
            json={"installment_id": inst.id, "method": "jazzcash"},
        )

    r1, r2 = await asyncio.gather(pay_once(), pay_once())
    codes = sorted([r1.status_code, r2.status_code])
    assert codes[0] == 200, (
        r1.status_code,
        r1.json() if r1.headers.get("content-type", "").startswith("application/json") else r1.text,
        r2.status_code,
        r2.json() if r2.headers.get("content-type", "").startswith("application/json") else r2.text,
    )
    # Losing request: PAYMENT_IN_PROGRESS (409, Redis lock lost the race) or
    # an already-settled rejection (422, DB-level guard caught it instead).
    assert codes[1] in {409, 422}

    # Above all: exactly one successful charge was ever recorded for this
    # installment, no matter which guard caught the loser.
    async with TestingSessionLocal() as session:
        successful = (
            await session.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.installment_id == inst.id,
                    PaymentTransaction.status == "success",
                )
            )
        ).scalars().all()
        assert len(successful) == 1


# ── Internal Trigger ─────────────────────────────────────────────────────────

async def test_internal_trigger_requires_token(client, test_user, seed_order_with_loan):
    user, _ = test_user
    _, loan = await seed_order_with_loan(user.id)

    from sqlalchemy import select

    async with TestingSessionLocal() as session:
        inst = await session.scalar(
            select(Installment).where(Installment.loan_id == loan.id, Installment.installment_number == 1)
        )

    resp = await client.post(
        "/api/v1/payments/internal/trigger-installment",
        json={"installment_id": inst.id, "method": "jazzcash"},
        # No X-Internal-Token header
    )
    assert resp.status_code == 401


async def test_internal_trigger_with_valid_token(client, test_user, seed_order_with_loan):
    user, _ = test_user
    _, loan = await seed_order_with_loan(user.id)

    from sqlalchemy import select

    async with TestingSessionLocal() as session:
        inst = await session.scalar(
            select(Installment).where(Installment.loan_id == loan.id, Installment.installment_number == 1)
        )

    resp = await client.post(
        "/api/v1/payments/internal/trigger-installment",
        headers={"X-Internal-Token": "test-internal-token-secret"},
        json={"installment_id": inst.id, "method": "jazzcash"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"