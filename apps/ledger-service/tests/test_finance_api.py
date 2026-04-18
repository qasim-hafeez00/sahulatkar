import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from sk_shared.models.ledger import JournalEntry, LateFeeCharityAllocation
from sk_shared.models.payment import Installment, Loan, PaymentTransaction
from src.services.accounting_service import AccountingService
from src.config import settings


@pytest.mark.asyncio
async def test_finance_pl_requires_admin_role(client):
    response = await client.get("/admin/finance/pl", params={"period": "2026-Q1"})
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


@pytest.mark.asyncio
async def test_finance_pl_rejects_wrong_admin_role(client):
    response = await client.get(
        "/admin/finance/pl",
        params={"period": "2026-Q1"},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "ops_agent"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "INSUFFICIENT_ADMIN_ROLE"


@pytest.mark.asyncio
async def test_finance_pl_allows_finance_admin(client):
    response = await client.get(
        "/admin/finance/pl",
        params={"period": "2026-Q1"},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["period"] == "2026-Q1"


@pytest.mark.asyncio
async def test_reconciliation_get_requires_admin_role(client):
    response = await client.get("/admin/finance/reconciliation")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


@pytest.mark.asyncio
async def test_shariah_get_requires_admin_role(client):
    response = await client.get("/admin/finance/shariah-audit", params={"period": "2026-Q1"})
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


@pytest.mark.asyncio
async def test_reconciliation_import_rejects_invalid_internal_token(client):
    response = await client.post(
        "/admin/finance/reconciliation",
        json={
            "gateway": "safepay",
            "settlement_date": "2026-04-01",
            "expected_amount": "100.00",
            "actual_amount": "100.00",
        },
        headers={"X-Internal-Token": "invalid"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "INVALID_INTERNAL_TOKEN"


@pytest.mark.asyncio
async def test_reconciliation_import_accepts_valid_internal_token(client):
    response = await client.post(
        "/admin/finance/reconciliation",
        json={
            "gateway": "safepay",
            "settlement_date": "2026-04-01",
            "expected_amount": "100.00",
            "actual_amount": "100.00",
        },
        headers={"X-Internal-Token": settings.internal_api_token},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"matched", "variance"}


@pytest.mark.asyncio
async def test_reconciliation_import_marks_matching_transactions_reconciled(client, db_session):
    txn = PaymentTransaction(
        user_id=99,
        gateway="safepay",
        amount=100,
        currency="PKR",
        status="success",
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)

    settlement_date = (txn.created_at.date() if txn.created_at else date.today()).isoformat()
    response = await client.post(
        "/admin/finance/reconciliation",
        json={
            "gateway": "safepay",
            "settlement_date": settlement_date,
            "expected_amount": "100.00",
            "actual_amount": "100.00",
        },
        headers={"X-Internal-Token": settings.internal_api_token},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched_transaction_count"] >= 1

    await db_session.refresh(txn)
    assert txn.reconciled_at is not None


@pytest.mark.asyncio
async def test_profit_loss_is_period_filtered(client, db_session, seed_ledger_accounts):
    service = AccountingService(db_session)

    await service.record_purchase(order_id=501, cost_amount=Decimal("100.00"), total_amount=Decimal("130.00"), vcn_id=1501)
    await service.record_purchase(order_id=502, cost_amount=Decimal("200.00"), total_amount=Decimal("260.00"), vcn_id=1502)

    q1_entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.source_id == 1501))).scalar_one()
    q2_entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.source_id == 1502))).scalar_one()
    q1_entry.entry_date = date(2026, 1, 15)
    q2_entry.entry_date = date(2026, 4, 15)
    await db_session.commit()

    response = await client.get(
        "/admin/finance/pl",
        params={"period": "2026-Q1"},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["revenue"] == pytest.approx(30.0)
    assert payload["net_income"] == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_trial_balance_endpoint(client, db_session, seed_ledger_accounts):
    service = AccountingService(db_session)
    await service.record_down_payment(order_id=701, amount=Decimal("2600.00"))

    response = await client.get(
        "/admin/finance/trial-balance",
        params={"period": str(date.today().year)},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_balanced"] is True
    assert payload["total_debit"] == pytest.approx(payload["total_credit"])
    assert len(payload["entries"]) >= 2


@pytest.mark.asyncio
async def test_balance_sheet_endpoint(client, db_session, seed_ledger_accounts):
    service = AccountingService(db_session)
    await service.record_down_payment(order_id=801, amount=Decimal("1000.00"))

    response = await client.get(
        "/admin/finance/balance-sheet",
        params={"as_of": date.today().isoformat()},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_balanced"] is True
    assert payload["total_assets"] == pytest.approx(payload["total_liabilities_and_equity"])


@pytest.mark.asyncio
async def test_invalid_period_returns_422(client):
    response = await client.get(
        "/admin/finance/pl",
        params={"period": "bad-period"},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "INVALID_PERIOD_FORMAT"


@pytest.mark.asyncio
async def test_invalid_as_of_returns_422(client):
    response = await client.get(
        "/admin/finance/balance-sheet",
        params={"as_of": "not-a-date"},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "INVALID_AS_OF_DATE"


@pytest.mark.asyncio
async def test_invalid_settlement_date_returns_422(client):
    response = await client.get(
        "/admin/finance/reconciliation",
        params={"settlement_date": "invalid-date"},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "INVALID_SETTLEMENT_DATE"


@pytest.mark.asyncio
async def test_shariah_audit_ratio_is_computed_not_hardcoded(client, db_session, seed_ledger_accounts):
    loan = Loan(
        order_id=910,
        user_id=910,
        loan_number="L-910",
        principal_amount=10000,
        profit_amount=400,
        total_repayable=10400,
        down_payment_amount=2600,
        balance_financed=7800,
        profit_rate_pct=4,
        plan_type="pay_in_4",
        installment_count=4,
        installment_amount=2600,
    )
    db_session.add(loan)
    await db_session.flush()

    inst = Installment(
        loan_id=loan.id,
        user_id=loan.user_id,
        installment_number=2,
        principal_portion=2500,
        profit_portion=100,
        total_amount=2600,
        due_date=date.today(),
        status="overdue",
    )
    db_session.add(inst)
    await db_session.commit()

    service = AccountingService(db_session)
    await service.record_late_fee(inst.id, Decimal("100.00"))

    allocation = (
        await db_session.execute(
            select(LateFeeCharityAllocation).where(LateFeeCharityAllocation.installment_id == inst.id)
        )
    ).scalar_one()
    allocation.late_fee_amount = Decimal("50.00")
    await db_session.commit()

    response = await client.get(
        "/admin/finance/shariah-audit",
        params={"period": str(date.today().year)},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["charity_routing_ratio"] == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_charity_report_requires_admin_role(client):
    response = await client.get("/admin/finance/charity-report", params={"period": str(date.today().year)})
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


@pytest.mark.asyncio
async def test_charity_report_returns_summary(client, db_session, seed_ledger_accounts):
    loan = Loan(
        order_id=920,
        user_id=920,
        loan_number="L-920",
        principal_amount=10000,
        profit_amount=400,
        total_repayable=10400,
        down_payment_amount=2600,
        balance_financed=7800,
        profit_rate_pct=4,
        plan_type="pay_in_4",
        installment_count=4,
        installment_amount=2600,
    )
    db_session.add(loan)
    await db_session.flush()

    inst = Installment(
        loan_id=loan.id,
        user_id=loan.user_id,
        installment_number=2,
        principal_portion=2500,
        profit_portion=100,
        total_amount=2600,
        due_date=date.today(),
        status="overdue",
    )
    db_session.add(inst)
    await db_session.commit()

    service = AccountingService(db_session)
    await service.record_late_fee(inst.id, Decimal("100.00"))

    response = await client.get(
        "/admin/finance/charity-report",
        params={"period": str(date.today().year)},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["allocated"] >= 100.0
    assert isinstance(payload["by_org"], list)


@pytest.mark.asyncio
async def test_charity_disbursement_requires_super_admin(client):
    response = await client.post(
        "/admin/finance/charity-disbursement",
        json={"allocation_ids": [1], "payment_reference": "ref-1", "receipt_s3": "s3://bucket/r1.pdf"},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "INSUFFICIENT_ADMIN_ROLE"


@pytest.mark.asyncio
async def test_charity_disbursement_marks_allocations_disbursed(client, db_session, seed_ledger_accounts):
    loan = Loan(
        order_id=930,
        user_id=930,
        loan_number="L-930",
        principal_amount=10000,
        profit_amount=400,
        total_repayable=10400,
        down_payment_amount=2600,
        balance_financed=7800,
        profit_rate_pct=4,
        plan_type="pay_in_4",
        installment_count=4,
        installment_amount=2600,
    )
    db_session.add(loan)
    await db_session.flush()

    inst = Installment(
        loan_id=loan.id,
        user_id=loan.user_id,
        installment_number=2,
        principal_portion=2500,
        profit_portion=100,
        total_amount=2600,
        due_date=date.today(),
        status="overdue",
    )
    db_session.add(inst)
    await db_session.commit()

    service = AccountingService(db_session)
    await service.record_late_fee(inst.id, Decimal("100.00"))
    allocation = (
        await db_session.execute(
            select(LateFeeCharityAllocation).where(LateFeeCharityAllocation.installment_id == inst.id)
        )
    ).scalar_one()

    response = await client.post(
        "/admin/finance/charity-disbursement",
        json={
            "allocation_ids": [allocation.id],
            "payment_reference": "ref-930",
            "receipt_s3": "s3://bucket/ref-930.pdf",
        },
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "super_admin"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["updated_count"] == 1
    assert payload["status"] == "disbursed"

    await db_session.refresh(allocation)
    assert allocation.disbursed_at is not None
    assert allocation.receipt_s3 == "s3://bucket/ref-930.pdf"


@pytest.mark.asyncio
async def test_request_id_header_is_propagated(client):
    response = await client.get("/health/live", headers={"X-Request-ID": "req-123"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "req-123"
