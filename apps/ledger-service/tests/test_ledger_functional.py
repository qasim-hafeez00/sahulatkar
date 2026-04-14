import pytest
from decimal import Decimal
from datetime import date, datetime, timezone
from sqlalchemy import select, func
from unittest.mock import AsyncMock

from sqlalchemy.orm import selectinload
from sk_shared.models.ledger import JournalEntry, JournalEntryLine, LateFeeCharityAllocation
from sk_shared.models.payment import Installment, Loan
from src.services.accounting_service import AccountingService
from src.billing.billing_sweep import BillingSweepService

@pytest.mark.asyncio
async def test_murabaha_lifecycle_ledger_entries(db_session, seed_ledger_accounts):
    service = AccountingService(db_session)
    
    # 1. Record Down Payment
    order_id = 123
    dp_amount = Decimal("2600.00")
    await service.record_down_payment(order_id, dp_amount)
    
    # Verify DP entry
    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .where(JournalEntry.entry_type == "payment_received", JournalEntry.source_id == order_id)
    )
    entry = (await db_session.execute(stmt)).scalar_one()
    assert entry.total_debit == dp_amount
    assert len(entry.lines) == 2
    
    # 2. Record Purchase (Murabaha Sale)
    cost = Decimal("10000.00")
    total = Decimal("10400.00")
    vcn_id = 789
    await service.record_purchase(order_id, cost, total, vcn_id)
    
    # Verify Sale entry
    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account))
        .where(JournalEntry.entry_type == "vcn_charge", JournalEntry.source_id == vcn_id)
    )
    entry = (await db_session.execute(stmt)).scalar_one()
    assert entry.total_debit == total
    assert any(line.account.account_code == "4001" and line.credit_amount == Decimal("400.00") for line in entry.lines)
    assert any(line.account.account_code == "1100" and line.debit_amount == total for line in entry.lines)

@pytest.mark.asyncio
async def test_late_fee_allocation(db_session, seed_ledger_accounts):
    # Setup a mock loan and installment
    loan = Loan(
        order_id=1, user_id=1, loan_number="L-001", 
        principal_amount=10000, profit_amount=400, total_repayable=10400,
        down_payment_amount=2600, balance_financed=7800, profit_rate_pct=4,
        plan_type="pay_in_4", installment_count=4, installment_amount=2600
    )
    db_session.add(loan)
    await db_session.flush()
    
    inst = Installment(
        loan_id=loan.id, user_id=1, installment_number=2,
        principal_portion=2500, profit_portion=100, total_amount=2600,
        due_date=date.today(), status="pending"
    )
    db_session.add(inst)
    await db_session.commit()
    
    service = AccountingService(db_session)
    late_fee = Decimal("150.00")
    await service.record_late_fee(inst.id, late_fee)
    
    # Verify ledger entry
    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account))
        .where(JournalEntry.entry_type == "late_fee", JournalEntry.source_id == inst.id)
    )
    entry = (await db_session.execute(stmt)).scalar_one()
    assert any(line.account.account_code == "2100" and line.credit_amount == late_fee for line in entry.lines)
    
    # Verify charity allocation
    stmt = select(LateFeeCharityAllocation).where(LateFeeCharityAllocation.installment_id == inst.id)
    alloc = (await db_session.execute(stmt)).scalar_one()
    assert alloc.late_fee_amount == late_fee

@pytest.mark.asyncio
async def test_billing_sweep_execution(db_session, seed_ledger_accounts, monkeypatch):
    # Setup due installment
    loan = Loan(
        order_id=2, user_id=2, loan_number="L-002", 
        principal_amount=10000, profit_amount=400, total_repayable=10400,
        down_payment_amount=2600, balance_financed=7800, profit_rate_pct=4,
        plan_type="pay_in_4", installment_count=4, installment_amount=2600
    )
    db_session.add(loan)
    await db_session.flush()
    
    inst = Installment(
        loan_id=loan.id, user_id=2, installment_number=2,
        principal_portion=2500, profit_portion=100, total_amount=2600,
        due_date=date.today(), status="pending"
    )
    db_session.add(inst)
    await db_session.commit()
    
    # Mock httpx to simulate payment success
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code
        def json(self): return self.json_data
        
    async def mock_post(*args, **kwargs):
        return MockResponse({"status": "success", "txn_id": 999}, 200)
    
    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    
    sweep_service = BillingSweepService(db_session)
    stats = await sweep_service.execute_sweep()
    
    assert stats["success"] == 1
    
    # Verify ledger entry was created
    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .where(JournalEntry.entry_type == "payment_received", JournalEntry.source_type == "installment.paid")
    )
    assert (await db_session.execute(stmt)).scalar_one() is not None
