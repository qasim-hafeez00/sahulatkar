import pytest
from sk_shared.models.payment import Installment, Loan
from src.billing.overdue_processor import OverdueProcessor


@pytest.mark.asyncio
async def test_readonly_guard_prevents_installment_update(db_session):
    """
    Test that mark_overdue_batch does NOT update the installments table.
    (BV-01/BV-05 boundary violation guard)
    """
    loan = Loan(
        order_id=9001,
        user_id=9001,
        loan_number="L-9001",
        principal_amount=5000,
        profit_amount=200,
        total_repayable=5200,
        down_payment_amount=1000,
        balance_financed=4200,
        profit_rate_pct=4,
        plan_type="pay_in_4",
        installment_count=4,
        installment_amount=1300,
    )
    db_session.add(loan)
    await db_session.flush()

    from datetime import date, timedelta
    inst = Installment(
        loan_id=loan.id,
        user_id=loan.user_id,
        installment_number=1,
        principal_portion=1200,
        profit_portion=100,
        total_amount=1300,
        due_date=date.today() - timedelta(days=5),
        status="pending",
    )
    db_session.add(inst)
    await db_session.commit()

    processor = OverdueProcessor(db_session, publisher=None)
    await processor.mark_overdue_batch([inst.id], as_of=date.today())

    # Verify status in DB is still "pending" — processor only emits event
    await db_session.refresh(inst)
    assert inst.status == "pending", (
        "BV-01 violated: ledger-service must not write 'overdue' status to installments table"
    )


@pytest.mark.asyncio
async def test_overdue_processor_does_not_write_to_db(db_session):
    """
    Test that OverdueProcessor only emits events and doesn't modify the database directly.
    """
    from datetime import date, timedelta

    loan = Loan(
        order_id=9002,
        user_id=9002,
        loan_number="L-9002",
        principal_amount=5000,
        profit_amount=200,
        total_repayable=5200,
        down_payment_amount=1000,
        balance_financed=4200,
        profit_rate_pct=4,
        plan_type="pay_in_4",
        installment_count=4,
        installment_amount=1300,
    )
    db_session.add(loan)
    await db_session.flush()

    installment = Installment(
        loan_id=loan.id,
        user_id=loan.user_id,
        installment_number=1,
        principal_portion=1200,
        profit_portion=100,
        total_amount=1300,
        due_date=date.today() - timedelta(days=5),
        status="pending",
    )
    db_session.add(installment)
    await db_session.commit()

    processor = OverdueProcessor(db_session, publisher=None)
    count = await processor.mark_overdue_batch([installment.id], as_of=date.today())
    assert count == 1

    # Verify status in DB is still "pending" (since processor only emits event)
    await db_session.refresh(installment)
    assert installment.status == "pending"
