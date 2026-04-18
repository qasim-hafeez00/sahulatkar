from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from sk_shared.models.ledger import LateFeeCharityAllocation
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
