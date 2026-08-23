from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import Installment
from src.events.publisher import EventPublisher


class OverdueProcessor:
    def __init__(self, db_session: AsyncSession, publisher: EventPublisher | None = None) -> None:
        self.db = db_session
        self.publisher = publisher

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
        """
        Detect overdue installments and publish event for Payment Orchestrator.
        Ledger service DOES NOT write to the installments table.
        """
        if not installment_ids:
            return 0

        # BV-01 & BV-05: We no longer update the installments table directly.
        # Instead, we publish an event and return the count of detected installments.
        if self.publisher:
            await self.publisher.publish_installments_overdue(installment_ids, as_of.isoformat())

        return len(installment_ids)

    async def compute_late_fee_amount(self, installment: Installment, days_overdue: int) -> Decimal:
        """
        P1-03: Configurable late fee policy.
        Fetches 'late_fee_fixed_amount' from system_parameters.
        """
        if installment.late_fee_waived:
            return Decimal("0.00")
        if days_overdue <= 0:
            return Decimal("0.00")
        if installment.late_fee_amount and Decimal(str(installment.late_fee_amount)) > Decimal("0.00"):
            return Decimal("0.00")

        from sk_shared.models.admin import SystemParameter
        stmt = select(SystemParameter.param_value).where(SystemParameter.param_key == "late_fee_fixed_amount")
        res = (await self.db.execute(stmt)).scalar_one_or_none()
        
        default_fee = Decimal("150.00")
        if res:
            try:
                return Decimal(res)
            except (ValueError, TypeError):
                return default_fee
        return default_fee
