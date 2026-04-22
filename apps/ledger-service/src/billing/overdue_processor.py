from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import Installment


class OverdueProcessor:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def find_newly_overdue(self, as_of: date, max_retries: int = 4) -> list[Installment]:
        grace_date = as_of - timedelta(days=1)
        stmt = (
            select(Installment)
            .where(Installment.status == "pending")
            .where(
                or_(
                    (Installment.due_date < as_of) & (Installment.retry_count >= max_retries),
                    Installment.due_date < grace_date,
                )
            )
            .order_by(Installment.due_date.asc(), Installment.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def mark_overdue_batch(self, installment_ids: list[int], as_of: date) -> int:
        if not installment_ids:
            return 0

        stmt = (
            update(Installment)
            .where(Installment.id.in_(installment_ids), Installment.status == "pending")
            .values(status="overdue")
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)

        # Refresh days_overdue in-session for predictable behavior.
        rows_stmt = select(Installment).where(Installment.id.in_(installment_ids))
        rows = (await self.db.execute(rows_stmt)).scalars().all()
        for inst in rows:
            if inst.due_date < as_of:
                inst.days_overdue = (as_of - inst.due_date).days
            else:
                inst.days_overdue = 0

        await self.db.commit()
        return int(result.rowcount or 0)

    def compute_late_fee_amount(self, installment: Installment, days_overdue: int) -> Decimal:
        if installment.late_fee_waived:
            return Decimal("0.00")
        if days_overdue <= 0:
            return Decimal("0.00")
        if installment.late_fee_amount and Decimal(str(installment.late_fee_amount)) > Decimal("0.00"):
            return Decimal("0.00")
        return Decimal("150.00")
