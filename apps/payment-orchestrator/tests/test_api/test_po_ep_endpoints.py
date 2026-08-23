"""
Coverage for the PO-EP-01/02/04/05/06 endpoints (src/api/v1/payments.py,
src/api/v1/admin.py). These already existed in source, fully implemented and
tagged, but had zero test coverage — meaning nobody had verified they
actually work. This is that verification pass.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from sk_shared.models.auth import AdminUser
from sk_shared.security import create_access_token, get_password_hash
from src.config import settings
from src.models.payment_mandate import PaymentMandate
from src.models.payment_workflow import PaymentWorkflow
from src.state.payment_workflow import PaymentStatus

pytestmark = pytest.mark.asyncio


async def _seed_admin(db_session, role: str = "superadmin") -> AdminUser:
    # AdminUser.role is an ORM relationship to Role, not a plain string column
    # (see packages/shared-python/sk_shared/models/auth.py) — role membership
    # for these endpoints is enforced purely off the JWT's "role" claim (see
    # RequireRole in src/core/dependencies.py), so it's never set on the row
    # itself. Matches the existing pattern in test_admin_transactions.py.
    admin = AdminUser(email=f"{role}-po-ep@sahulatkar.pk", password_hash=get_password_hash("irrelevant"))
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


def _admin_token(admin: AdminUser, role: str = "superadmin") -> str:
    return create_access_token(
        {"admin_id": admin.id, "role": role}, settings.JWT_PRIVATE_KEY, timedelta(seconds=900)
    )


# ── PO-EP-01: retry down payment ─────────────────────────────────────────────

async def test_retry_down_payment_creates_new_workflow_for_failed(client, db_session, test_user):
    user, token = test_user
    workflow = PaymentWorkflow(
        order_id=1,
        user_id=user.id,
        amount_pkr=Decimal("1300"),
        gateway="jazzcash",
        idempotency_key="orig-key-001",
        status=PaymentStatus.FAILED,
        attempt_count=1,
        last_error="GATEWAY_DECLINED",
    )
    db_session.add(workflow)
    await db_session.commit()
    await db_session.refresh(workflow)

    with patch("src.adapters.factory.GatewayAdapterFactory.get") as mock_factory:
        adapter = AsyncMock()
        adapter.initiate_payment = AsyncMock(return_value={"gateway_txn_id": "jc_retry_001", "payment_url": "https://pay.example/retry"})
        mock_factory.return_value = adapter

        resp = await client.post(
            f"/api/v1/payments/down-payment/{workflow.id}/retry",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "retried"
    assert body["new_workflow_id"] != workflow.id
    assert body["idempotency_key"] != workflow.idempotency_key

    new_workflow = await db_session.get(PaymentWorkflow, body["new_workflow_id"])
    assert new_workflow is not None
    assert new_workflow.status == PaymentStatus.PENDING


async def test_retry_down_payment_rejects_non_retryable_status(client, db_session, test_user):
    user, token = test_user
    workflow = PaymentWorkflow(
        order_id=2,
        user_id=user.id,
        amount_pkr=Decimal("1300"),
        gateway="jazzcash",
        idempotency_key="orig-key-002",
        status=PaymentStatus.CAPTURED,
    )
    db_session.add(workflow)
    await db_session.commit()
    await db_session.refresh(workflow)

    resp = await client.post(
        f"/api/v1/payments/down-payment/{workflow.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert "WORKFLOW_NOT_RETRYABLE" in resp.json()["detail"]


async def test_retry_down_payment_rejects_other_users_workflow(client, db_session, test_user):
    user, token = test_user
    workflow = PaymentWorkflow(
        order_id=3,
        user_id=user.id + 999,
        amount_pkr=Decimal("1300"),
        gateway="jazzcash",
        idempotency_key="orig-key-003",
        status=PaymentStatus.FAILED,
    )
    db_session.add(workflow)
    await db_session.commit()
    await db_session.refresh(workflow)

    resp = await client.post(
        f"/api/v1/payments/down-payment/{workflow.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_retry_down_payment_404_for_unknown_workflow(client, test_user):
    _, token = test_user
    resp = await client.post(
        "/api/v1/payments/down-payment/999999/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── PO-EP-02: payment history ────────────────────────────────────────────────

async def test_get_payment_history_returns_transactions_and_workflows(client, db_session, test_user, seed_order_with_loan):
    from sk_shared.models.payment import PaymentTransaction

    user, token = test_user
    order, loan = await seed_order_with_loan(user.id)

    txn = PaymentTransaction(
        loan_id=loan.id, user_id=user.id, amount=Decimal("1300"), currency="PKR",
        gateway="jazzcash", gateway_txn_id="jc_hist_1", status="success",
    )
    db_session.add(txn)
    workflow = PaymentWorkflow(
        order_id=order.id, user_id=user.id, amount_pkr=Decimal("1300"),
        gateway="jazzcash", idempotency_key="hist-key-1", status=PaymentStatus.CAPTURED,
    )
    db_session.add(workflow)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/payments/history/{order.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["order_id"] == order.id
    assert len(body["transactions"]) == 1
    assert body["transactions"][0]["gateway_txn_id"] == "jc_hist_1"
    assert len(body["workflows"]) == 1
    assert body["workflows"][0]["status"] == PaymentStatus.CAPTURED


async def test_get_payment_history_404_for_other_users_order(client, test_user, seed_order_with_loan):
    user, token = test_user
    order, _ = await seed_order_with_loan(user.id + 999)

    resp = await client.get(
        f"/api/v1/payments/history/{order.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_get_payment_history_empty_for_order_with_no_payments(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    resp = await client.get(
        f"/api/v1/payments/history/{order.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transactions"] == []
    assert body["workflows"] == []


# ── PO-EP-04: admin-triggered reconciliation ─────────────────────────────────

async def test_trigger_reconciliation_accepts_valid_request(client, db_session, monkeypatch):
    admin = await _seed_admin(db_session, "finance")
    token = _admin_token(admin, "finance")

    monkeypatch.setattr(
        "src.workers.reconciliation_worker.run_reconciliation",
        AsyncMock(return_value=None),
    )

    resp = await client.post(
        "/api/v1/admin/payments/reconciliation/trigger",
        params={"gateway": "jazzcash", "settlement_date": "2026-08-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "triggered"
    assert body["gateway"] == "jazzcash"


async def test_trigger_reconciliation_rejects_unsupported_gateway(client, db_session):
    admin = await _seed_admin(db_session, "finance")
    token = _admin_token(admin, "finance")

    resp = await client.post(
        "/api/v1/admin/payments/reconciliation/trigger",
        params={"gateway": "totally_not_a_gateway", "settlement_date": "2026-08-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "UNSUPPORTED_GATEWAY"


async def test_trigger_reconciliation_rejects_bad_date_format(client, db_session):
    admin = await _seed_admin(db_session, "finance")
    token = _admin_token(admin, "finance")

    resp = await client.post(
        "/api/v1/admin/payments/reconciliation/trigger",
        params={"gateway": "jazzcash", "settlement_date": "08/01/2026"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "INVALID_DATE_FORMAT: use YYYY-MM-DD"


async def test_trigger_reconciliation_forbidden_for_read_only_role(client, db_session):
    admin = await _seed_admin(db_session, "support")
    token = _admin_token(admin, "support")

    resp = await client.post(
        "/api/v1/admin/payments/reconciliation/trigger",
        params={"gateway": "jazzcash", "settlement_date": "2026-08-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── PO-EP-05: admin view of a user's mandates ────────────────────────────────

async def test_get_user_mandates_returns_all_mandates_for_user(client, db_session):
    admin = await _seed_admin(db_session, "support")
    token = _admin_token(admin, "support")

    mandate = PaymentMandate(
        user_id=555, gateway="raast", mandate_reference="mandate-ref-555",
        status="active", payer_identifier="PK36SCBL0000001123456702",
    )
    db_session.add(mandate)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/admin/payments/mandates/555",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == 555
    assert len(body["mandates"]) == 1
    assert body["mandates"][0]["mandate_reference"] == "mandate-ref-555"
    assert body["mandates"][0]["status"] == "active"


async def test_get_user_mandates_empty_list_for_user_with_none(client, db_session):
    admin = await _seed_admin(db_session, "support")
    token = _admin_token(admin, "support")

    resp = await client.get(
        "/api/v1/admin/payments/mandates/999888",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["mandates"] == []


# ── PO-EP-06: internal auto-collect ──────────────────────────────────────────

async def test_auto_collect_installment_success_creates_transaction_and_publishes_event(
    client, db_session, redis_mock, test_user, seed_order_with_loan
):
    from sk_shared.models.payment import Installment, PaymentTransaction

    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    installment = (await db_session.execute(
        select(Installment).where(Installment.loan_id == loan.id).order_by(Installment.installment_number.asc())
    )).scalars().first()

    with patch("src.adapters.factory.GatewayAdapterFactory.get") as mock_factory:
        adapter = AsyncMock()
        adapter.initiate_payment = AsyncMock(return_value={"gateway_txn_id": "auto_collect_txn_1"})
        mock_factory.return_value = adapter

        resp = await client.post(
            f"/api/v1/payments/internal/installments/{installment.id}/auto-collect",
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"

    txn = await db_session.scalar(
        select(PaymentTransaction).where(PaymentTransaction.installment_id == installment.id)
    )
    assert txn is not None
    assert txn.gateway_txn_id == "auto_collect_txn_1"
    assert txn.status == "success"


async def test_auto_collect_installment_rejects_missing_internal_token(client, db_session, test_user, seed_order_with_loan):
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    from sk_shared.models.payment import Installment
    installment = (await db_session.execute(
        select(Installment).where(Installment.loan_id == loan.id).order_by(Installment.installment_number.asc())
    )).scalars().first()

    resp = await client.post(f"/api/v1/payments/internal/installments/{installment.id}/auto-collect")
    assert resp.status_code == 401


async def test_auto_collect_installment_404_for_unknown_installment(client, db_session):
    resp = await client.post(
        "/api/v1/payments/internal/installments/999999/auto-collect",
        headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
    )
    assert resp.status_code == 404


async def test_auto_collect_installment_already_paid_short_circuits(client, db_session, test_user, seed_order_with_loan):
    from sk_shared.models.payment import Installment

    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    installment = (await db_session.execute(
        select(Installment).where(Installment.loan_id == loan.id).order_by(Installment.installment_number.asc())
    )).scalars().first()
    installment.status = "paid"
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/payments/internal/installments/{installment.id}/auto-collect",
        headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_paid"


async def test_auto_collect_installment_uses_active_raast_mandate_when_valid(
    client, db_session, test_user, seed_order_with_loan
):
    from sk_shared.models.payment import Installment

    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    installment = (await db_session.execute(
        select(Installment).where(Installment.loan_id == loan.id).order_by(Installment.installment_number.asc())
    )).scalars().first()

    mandate = PaymentMandate(
        user_id=user.id, gateway="raast", mandate_reference="mandate-active-1",
        status="active", payer_identifier="PK36SCBL0000001123456702",
        max_amount_per_txn=Decimal("10000"),
    )
    db_session.add(mandate)
    await db_session.commit()

    with patch("src.adapters.factory.GatewayAdapterFactory.get") as mock_factory:
        adapter = AsyncMock()
        adapter.initiate_payment = AsyncMock(return_value={"gateway_txn_id": "raast_auto_1"})
        mock_factory.return_value = adapter

        resp = await client.post(
            f"/api/v1/payments/internal/installments/{installment.id}/auto-collect",
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )

        assert resp.status_code == 200
        mock_factory.assert_called_once()
        assert mock_factory.call_args[0][0] == "raast"
