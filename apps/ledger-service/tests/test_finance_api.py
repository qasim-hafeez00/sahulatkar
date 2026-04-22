import pytest
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from sk_shared.models.ledger import JournalEntry, LateFeeCharityAllocation
from sk_shared.models.payment import Installment, Loan, PaymentTransaction
from src.services.accounting_service import AccountingService
from src.accounting.accounts import ACCOUNT_CODES
from src.config import settings
from src.events.dlq import EventDeadLetterQueue


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
async def test_reconciliation_import_rejects_negative_amount(client):
    response = await client.post(
        "/admin/finance/reconciliation",
        json={
            "gateway": "safepay",
            "settlement_date": "2026-04-01",
            "expected_amount": "-1.00",
            "actual_amount": "100.00",
        },
        headers={"X-Internal-Token": settings.internal_api_token},
    )
    assert response.status_code == 422


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

    # BV-02: ledger-service now publishes EVENT_LEDGER_RECONCILIATION_MATCHED instead of writing directly
    await db_session.refresh(txn)
    assert txn.reconciled_at is None


@pytest.mark.asyncio
async def test_profit_loss_is_period_filtered(client, db_session, seed_ledger_accounts):
    service = AccountingService(db_session)

    await service.record_purchase(order_id=501, cost_amount=Decimal("100.00"), total_amount=Decimal("130.00"), vcn_id=1501)
    await service.record_purchase(order_id=502, cost_amount=Decimal("200.00"), total_amount=Decimal("260.00"), vcn_id=1502)

    q1_entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.source_id == 1501))).scalar_one()
    q2_entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.source_id == 1502))).scalar_one()
    q1_entry.entry_date = date(2026, 1, 15)
    q1_entry.period_key = "2026-01"
    q2_entry.entry_date = date(2026, 4, 15)
    q2_entry.period_key = "2026-04"
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
async def test_accounts_get_requires_admin_role(client):
    response = await client.get("/admin/finance/accounts")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


@pytest.mark.asyncio
async def test_accounts_get_returns_filtered_balances(client, db_session, seed_ledger_accounts):
    service = AccountingService(db_session)
    await service.record_down_payment(order_id=880, amount=Decimal("1000.00"))

    response = await client.get(
        "/admin/finance/accounts",
        params={"account_type": "asset", "as_of": date.today().isoformat()},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["account_type_filter"] == "asset"
    cash = next((item for item in payload["items"] if item["account_code"] == ACCOUNT_CODES["cash"]), None)
    assert cash is not None
    assert cash["balance"] == pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_accounts_get_rejects_invalid_account_type(client):
    response = await client.get(
        "/admin/finance/accounts",
        params={"account_type": "invalid"},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "INVALID_ACCOUNT_TYPE"


@pytest.mark.asyncio
async def test_account_balance_endpoint_returns_balance(client, db_session, seed_ledger_accounts):
    service = AccountingService(db_session)
    await service.record_down_payment(order_id=881, amount=Decimal("2600.00"))

    response = await client.get(
        f"/admin/finance/accounts/{ACCOUNT_CODES['cash']}/balance",
        params={"as_of": date.today().isoformat()},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["account_code"] == ACCOUNT_CODES["cash"]
    assert payload["balance"] == pytest.approx(2600.0)


@pytest.mark.asyncio
async def test_account_balance_endpoint_returns_404_for_unknown_code(client):
    response = await client.get(
        "/admin/finance/accounts/9999/balance",
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "ACCOUNT_NOT_FOUND"


@pytest.mark.asyncio
async def test_journal_entries_get_requires_admin_role(client):
    response = await client.get("/admin/finance/entries")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


@pytest.mark.asyncio
async def test_journal_entries_get_returns_filtered_items(client, db_session, seed_ledger_accounts):
    service = AccountingService(db_session)
    await service.record_down_payment(order_id=991, amount=Decimal("1000.00"))
    await service.record_purchase(order_id=992, cost_amount=Decimal("800.00"), total_amount=Decimal("1000.00"), vcn_id=1992)

    response = await client.get(
        "/admin/finance/entries",
        params={"entry_type": "payment_received", "limit": 10},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["limit"] == 10
    assert len(payload["items"]) >= 1
    assert all(item["entry_type"] == "payment_received" for item in payload["items"])


@pytest.mark.asyncio
async def test_journal_entry_detail_returns_lines(client, db_session, seed_ledger_accounts):
    service = AccountingService(db_session)
    result = await service.record_down_payment(order_id=993, amount=Decimal("2600.00"))

    response = await client.get(
        f"/admin/finance/entries/{result.journal_entry.entry_number}",
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["entry_number"] == result.journal_entry.entry_number
    assert len(payload["lines"]) >= 2


@pytest.mark.asyncio
async def test_journal_entry_detail_returns_404_for_unknown_entry(client):
    response = await client.get(
        "/admin/finance/entries/JE-DOES-NOT-EXIST",
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "ENTRY_NOT_FOUND"


@pytest.mark.asyncio
async def test_journal_entries_reject_invalid_date_filter(client):
    response = await client.get(
        "/admin/finance/entries",
        params={"from_date": "invalid-date"},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "INVALID_DATE_FILTER"


@pytest.mark.asyncio
async def test_ar_aging_requires_admin_role(client):
    response = await client.get("/admin/finance/ar-aging")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


@pytest.mark.asyncio
async def test_ar_aging_returns_buckets_and_total(client, db_session):
    loan = Loan(
        order_id=995,
        user_id=995,
        loan_number="L-995",
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

    db_session.add_all(
        [
            Installment(
                loan_id=loan.id,
                user_id=loan.user_id,
                installment_number=1,
                principal_portion=900,
                profit_portion=100,
                total_amount=1000,
                paid_amount=200,
                due_date=date.today() - timedelta(days=10),
                status="pending",
            ),
            Installment(
                loan_id=loan.id,
                user_id=loan.user_id,
                installment_number=2,
                principal_portion=500,
                profit_portion=0,
                total_amount=500,
                paid_amount=0,
                due_date=date.today() - timedelta(days=40),
                status="overdue",
            ),
            Installment(
                loan_id=loan.id,
                user_id=loan.user_id,
                installment_number=3,
                principal_portion=300,
                profit_portion=0,
                total_amount=300,
                paid_amount=100,
                due_date=date.today() - timedelta(days=95),
                status="overdue",
            ),
            Installment(
                loan_id=loan.id,
                user_id=loan.user_id,
                installment_number=4,
                principal_portion=100,
                profit_portion=0,
                total_amount=100,
                paid_amount=0,
                due_date=date.today() + timedelta(days=5),
                status="pending",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/admin/finance/ar-aging",
        params={"as_of": date.today().isoformat()},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_outstanding"] == pytest.approx(1500.0)

    buckets = {item["bucket"]: item for item in payload["items"]}
    assert buckets["0-30"]["total_amount"] == pytest.approx(800.0)
    assert buckets["31-60"]["total_amount"] == pytest.approx(500.0)
    assert buckets["61-90"]["total_amount"] == pytest.approx(0.0)
    assert buckets["90+"]["total_amount"] == pytest.approx(200.0)


@pytest.mark.asyncio
async def test_ar_aging_filters_by_status(client, db_session):
    loan = Loan(
        order_id=996,
        user_id=996,
        loan_number="L-996",
        principal_amount=2000,
        profit_amount=100,
        total_repayable=2100,
        down_payment_amount=500,
        balance_financed=1600,
        profit_rate_pct=5,
        plan_type="pay_in_4",
        installment_count=4,
        installment_amount=525,
    )
    db_session.add(loan)
    await db_session.flush()

    db_session.add_all(
        [
            Installment(
                loan_id=loan.id,
                user_id=loan.user_id,
                installment_number=1,
                principal_portion=500,
                profit_portion=25,
                total_amount=525,
                paid_amount=0,
                due_date=date.today() - timedelta(days=15),
                status="pending",
            ),
            Installment(
                loan_id=loan.id,
                user_id=loan.user_id,
                installment_number=2,
                principal_portion=500,
                profit_portion=25,
                total_amount=525,
                paid_amount=0,
                due_date=date.today() - timedelta(days=15),
                status="overdue",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/admin/finance/ar-aging",
        params={"status": "overdue", "as_of": date.today().isoformat()},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["status"] == "overdue"
    assert payload["total_outstanding"] == pytest.approx(525.0)


@pytest.mark.asyncio
async def test_ar_aging_rejects_invalid_as_of(client):
    response = await client.get(
        "/admin/finance/ar-aging",
        params={"as_of": "not-a-date"},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "INVALID_AS_OF_DATE"


@pytest.mark.asyncio
async def test_dlq_list_requires_admin_role(client):
    response = await client.get("/admin/finance/dlq")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


@pytest.mark.asyncio
async def test_dlq_list_and_detail_endpoints(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    dlq = EventDeadLetterQueue()
    await dlq.push(
        event_name="payment.installment_paid",
        payload={"installment_id": 123, "amount_pkr": "100.00"},
        error=RuntimeError("test failure"),
        retry_count=1,
    )

    list_response = await client.get(
        "/admin/finance/dlq",
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total_messages"] >= 1
    message_id = list_payload["items"][0]["message_id"]

    detail_response = await client.get(
        f"/admin/finance/dlq/{message_id}",
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["event_name"] == "payment.installment_paid"
    assert detail_payload["retry_count"] == 1


@pytest.mark.asyncio
async def test_dlq_retry_requeues_event(client, redis_mock, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    dlq = EventDeadLetterQueue()
    await dlq.push(
        event_name="payment.installment_paid",
        payload={"installment_id": 999, "amount_pkr": "250.00"},
        error=ValueError("processing failed"),
        retry_count=2,
    )

    published: dict[str, str] = {}

    async def _capture_publish(channel: str, message: str) -> None:
        published["channel"] = channel
        published["message"] = message

    monkeypatch.setattr(redis_mock, "publish", _capture_publish)

    response = await client.post(
        "/admin/finance/dlq/1/retry",
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "super_admin"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "requeued"
    assert published["channel"] == "sk:events:payment.installment_paid"


@pytest.mark.asyncio
async def test_dlq_retry_requires_super_admin(client):
    response = await client.post(
        "/admin/finance/dlq/1/retry",
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "INSUFFICIENT_ADMIN_ROLE"


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
async def test_charity_disbursement_rejects_invalid_payload(client):
    response = await client.post(
        "/admin/finance/charity-disbursement",
        json={"allocation_ids": [1, 1], "payment_reference": " ", "receipt_s3": " "},
        headers={"X-Actor-Type": "admin", "X-Actor-Roles": "super_admin"},
    )
    assert response.status_code == 422


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
