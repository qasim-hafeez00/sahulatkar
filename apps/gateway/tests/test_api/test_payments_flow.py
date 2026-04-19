"""
test_payments_flow.py — Down payment initiation and payment schedule retrieval.
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_down_payment_requires_auth(client: AsyncClient):
    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": 1, "method": "safepay", "amount_pkr": "1000.00"},
    )
    assert r.status_code in {401, 403}


async def test_down_payment_blocked_when_not_contracts_signed(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    user, token = test_user
    order = Order(user_id=user.id, status="offer_accepted", total_amount=10000, product_description="test")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": order.id, "method": "jazzcash", "amount_pkr": "2500.00"},
        headers=_auth(token),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "CONTRACTS_NOT_SIGNED"


async def test_down_payment_amount_mismatch_rejected(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    user, token = test_user
    order = Order(
        user_id=user.id,
        status="contracts_signed",
        total_amount=10000,
        down_payment_amount=2500,
        product_description="test"
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": order.id, "method": "easypaisa", "amount_pkr": "5000.00"},
        headers=_auth(token),
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "DOWN_PAYMENT_AMOUNT_MISMATCH"


async def test_down_payment_succeeds_with_correct_amount(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    user, token = test_user
    order = Order(
        user_id=user.id,
        status="contracts_signed",
        total_amount=10000,
        down_payment_amount=2500,
        product_description="test"
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": order.id, "method": "raast", "amount_pkr": "2500.00"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "initiated"
    assert "payment_id" in body


async def test_down_payment_invalid_method_rejected(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    user, token = test_user
    order = Order(
        user_id=user.id,
        status="contracts_signed",
        total_amount=10000,
        down_payment_amount=2500,
        product_description="test"
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": order.id, "method": "paypal", "amount_pkr": "2500.00"},
        headers=_auth(token),
    )
    assert r.status_code == 422  # Pydantic pattern validation


async def test_payment_schedule_404_when_no_loan(client: AsyncClient, test_user):
    _, token = test_user
    r = await client.get("/api/v1/payments/schedule/999999", headers=_auth(token))
    assert r.status_code == 404
    assert r.json()["detail"] == "LOAN_NOT_FOUND"


async def test_vcn_blocked_without_down_payment(client: AsyncClient, test_user, db_session):
    """VCN must be blocked when order status is CONTRACTS_SIGNED (not DOWN_PAYMENT_RECEIVED)."""
    from sk_shared.models.order import Order
    user, token = test_user
    order = Order(user_id=user.id, status="contracts_signed", total_amount=10000, product_description="test")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id},
        headers=_auth(token),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "DOWN_PAYMENT_NOT_CONFIRMED"


async def test_installment_payment_succeeds(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    from sk_shared.models.payment import Loan, Installment

    user, token = test_user
    order = Order(user_id=user.id, status="contracts_signed", total_amount=10000, down_payment_amount=2500, product_description="test")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    loan = Loan(
        order_id=order.id,
        user_id=user.id,
        loan_number="LN-001",
        principal_amount=7500,
        profit_amount=500,
        total_repayable=8000,
        down_payment_amount=2500,
        balance_financed=7500,
        profit_rate_pct=5.0,
        plan_type="standard",
        installment_count=4,
        installment_amount=2000,
        status="active",
        total_paid=0,
        total_outstanding=8000,
        late_fee_total=0,
    )
    db_session.add(loan)
    await db_session.commit()
    await db_session.refresh(loan)

    installment = Installment(
        loan_id=loan.id,
        user_id=user.id,
        installment_number=1,
        is_down_payment=False,
        principal_portion=1800,
        profit_portion=200,
        total_amount=2000,
        due_date=loan.created_at.date(),
        status="pending",
        paid_amount=0,
        days_overdue=0,
        late_fee_amount=0,
        late_fee_waived=False,
        retry_count=0,
    )
    db_session.add(installment)
    await db_session.commit()
    await db_session.refresh(installment)

    r = await client.post(
        f"/api/v1/payments/installment/{installment.id}/pay",
        json={"method": "raast", "amount_pkr": "2000.00"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "initiated"
    assert "payment_id" in body


async def test_duplicate_down_payment_rejected(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order

    user, token = test_user
    order = Order(
        user_id=user.id,
        status="contracts_signed",
        total_amount=12000,
        down_payment_amount=3000,
        product_description="test"
    )
    db_session.add(order)
    await db_session.commit()

    payload = {"order_id": order.id, "method": "raast", "amount_pkr": "3000.00"}
    r1 = await client.post("/api/v1/payments/down-payment", json=payload, headers=_auth(token))
    assert r1.status_code == 200

    r2 = await client.post("/api/v1/payments/down-payment", json=payload, headers=_auth(token))
    assert r2.status_code == 409
    assert r2.json()["detail"] == "DOWN_PAYMENT_ALREADY_INITIATED"


async def test_installment_amount_mismatch_rejected(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    from sk_shared.models.payment import Loan, Installment

    user, token = test_user
    order = Order(user_id=user.id, status="contracts_signed", total_amount=10000, down_payment_amount=2500, product_description="test")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    loan = Loan(
        order_id=order.id,
        user_id=user.id,
        loan_number="LN-002",
        principal_amount=7500,
        profit_amount=500,
        total_repayable=8000,
        down_payment_amount=2500,
        balance_financed=7500,
        profit_rate_pct=5.0,
        plan_type="standard",
        installment_count=4,
        installment_amount=2000,
        status="active",
        total_paid=0,
        total_outstanding=8000,
        late_fee_total=0,
    )
    db_session.add(loan)
    await db_session.commit()
    await db_session.refresh(loan)

    installment = Installment(
        loan_id=loan.id,
        user_id=user.id,
        installment_number=1,
        is_down_payment=False,
        principal_portion=1800,
        profit_portion=200,
        total_amount=2000,
        due_date=loan.created_at.date(),
        status="pending",
        paid_amount=0,
        days_overdue=0,
        late_fee_amount=0,
        late_fee_waived=False,
        retry_count=0,
    )
    db_session.add(installment)
    await db_session.commit()

    r = await client.post(
        f"/api/v1/payments/installment/{installment.id}/pay",
        json={"method": "raast", "amount_pkr": "1500.00"},
        headers=_auth(token),
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "INSTALLMENT_AMOUNT_MISMATCH"


async def test_vcn_status_endpoint_returns_not_issued(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order

    user, token = test_user
    order = Order(user_id=user.id, status="pending_vcn", total_amount=10000, product_description="test")
    db_session.add(order)
    await db_session.commit()

    r = await client.get(f"/api/v1/payments/vcn/status/{order.id}", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["vcn_status"] == "not_issued"
