from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from sk_shared.models.ledger import JournalEntry, LateFeeCharityAllocation
from sk_shared.models.payment import Installment, Loan
from src.services.late_fee_service import LateFeeService


@pytest.mark.asyncio
async def test_apply_late_fee_creates_allocation(db_session, seed_ledger_accounts):
    loan = Loan(
        order_id=940,
        user_id=940,
        loan_number="L-940",
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

    service = LateFeeService(db_session)
    result = await service.apply_late_fee_to_installment(inst.id, Decimal("100.00"))
    assert result["status"] == "applied"

    allocation = (
        await db_session.execute(
            select(LateFeeCharityAllocation).where(LateFeeCharityAllocation.installment_id == inst.id)
        )
    ).scalar_one()
    assert Decimal(str(allocation.late_fee_amount)) == Decimal("100.00")


@pytest.mark.asyncio
async def test_apply_late_fee_twice_on_still_overdue_installment_is_idempotent(db_session, seed_ledger_accounts):
    """Regression test for the billing-sweep crash: an installment that is
    STILL overdue the day after it first went overdue gets returned by
    find_newly_overdue() again, so apply_late_fee_to_installment() can be
    called a second time for the same installment. Before the fix, the
    idempotency guard checked `installment.late_fee_amount`, a field nothing
    in the monorepo ever writes back, so it never tripped -- the second call
    fell all the way through to AccountingService.record_late_fee(), which
    unconditionally inserted a second LateFeeCharityAllocation and violated
    its UniqueConstraint(installment_id) on commit (IntegrityError).

    This must not crash, must not create a duplicate JournalEntry or
    LateFeeCharityAllocation, and the second call must be recognized as
    already-applied.
    """
    loan = Loan(
        order_id=941,
        user_id=941,
        loan_number="L-941",
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

    service = LateFeeService(db_session)

    # Day 1: installment goes overdue, late fee applied for the first time.
    first = await service.apply_late_fee_to_installment(inst.id, Decimal("100.00"))
    assert first["status"] == "applied"

    # Day 2: installment is STILL overdue (unpaid); the billing sweep's
    # find_newly_overdue() matches purely on due_date, regardless of whether
    # a fee was already charged, so the same installment is reprocessed.
    second = await service.apply_late_fee_to_installment(inst.id, Decimal("100.00"))
    assert second["status"] == "already_applied"
    assert second["amount"] == pytest.approx(100.0)

    # No duplicate rows -- exactly one allocation and one journal entry.
    allocations = (
        await db_session.execute(
            select(LateFeeCharityAllocation).where(LateFeeCharityAllocation.installment_id == inst.id)
        )
    ).scalars().all()
    assert len(allocations) == 1
    assert Decimal(str(allocations[0].late_fee_amount)) == Decimal("100.00")

    entries = (
        await db_session.execute(
            select(JournalEntry).where(
                JournalEntry.source_type == "installment.late_fee",
                JournalEntry.source_id == inst.id,
            )
        )
    ).scalars().all()
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_waive_and_summary(db_session):
    loan = Loan(
        order_id=950,
        user_id=950,
        loan_number="L-950",
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
        late_fee_amount=100,
    )
    db_session.add(inst)
    await db_session.commit()

    service = LateFeeService(db_session)
    waived = await service.waive_late_fee(inst.id, reason="first offense")
    assert waived["status"] == "waived"

    summary = await service.get_late_fee_summary(user_id=loan.user_id)
    assert summary["total_charged"] == pytest.approx(100.0)
    assert summary["total_waived"] == pytest.approx(100.0)
    assert summary["outstanding"] == pytest.approx(0.0)
