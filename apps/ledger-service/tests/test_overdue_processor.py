from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from sk_shared.models.payment import Installment, Loan
from src.billing.overdue_processor import OverdueProcessor


@pytest.mark.asyncio
async def test_find_and_mark_newly_overdue(db_session):
    loan = Loan(
        order_id=100,
        user_id=100,
        loan_number="L-100",
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

    old_due = date.today() - timedelta(days=3)
    inst = Installment(
        loan_id=loan.id,
        user_id=loan.user_id,
        installment_number=2,
        principal_portion=2500,
        profit_portion=100,
        total_amount=2600,
        due_date=old_due,
        status="pending",
        retry_count=0,
    )
    db_session.add(inst)
    await db_session.commit()

    processor = OverdueProcessor(db_session)
    candidates = await processor.find_newly_overdue(as_of=date.today())
    assert any(i.id == inst.id for i in candidates)

    # BV-01/BV-05: mark_overdue_batch no longer writes to the installments table;
    # it only emits an event and returns the count of detected installments.
    updated = await processor.mark_overdue_batch([inst.id], as_of=date.today())
    assert updated == 1

    # The status in DB remains 'pending' — it is the Payment Orchestrator's
    # responsibility to transition it to 'overdue' upon receiving the event.
    await db_session.refresh(inst)
    assert inst.status == "pending"


@pytest.mark.asyncio
async def test_compute_late_fee_policy(db_session):
    processor = OverdueProcessor(db_session)

    dummy = Installment(
        loan_id=1,
        user_id=1,
        installment_number=1,
        principal_portion=100,
        profit_portion=10,
        total_amount=110,
        due_date=date.today(),
        status="overdue",
        late_fee_waived=False,
        late_fee_amount=0,
    )
    # compute_late_fee_amount is now async (fetches from SystemParameter)
    assert await processor.compute_late_fee_amount(dummy, days_overdue=2) == Decimal("150.00")

    dummy.late_fee_waived = True
    assert await processor.compute_late_fee_amount(dummy, days_overdue=2) == Decimal("0.00")

    dummy.late_fee_waived = False
    dummy.late_fee_amount = 100
    assert await processor.compute_late_fee_amount(dummy, days_overdue=5) == Decimal("0.00")
