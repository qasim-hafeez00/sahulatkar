from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha1

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.ledger import CharityOrganization, LateFeeCharityAllocation
from src.services.accounting_service import AccountingService


class CharityService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def get_pending_disbursements(self, min_age_days: int = 7) -> list[LateFeeCharityAllocation]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
        stmt = (
            select(LateFeeCharityAllocation)
            .where(LateFeeCharityAllocation.deleted_at.is_(None))
            .where(LateFeeCharityAllocation.disbursed_at.is_(None))
            .where(LateFeeCharityAllocation.allocated_at <= cutoff)
            .order_by(LateFeeCharityAllocation.allocated_at.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def record_disbursement(self, allocation_ids: list[int], payment_reference: str, receipt_s3: str) -> dict[str, object]:
        if not allocation_ids:
            return {"updated_count": 0, "total_amount": 0.0, "status": "no_allocations"}

        stmt = (
            select(LateFeeCharityAllocation)
            .where(LateFeeCharityAllocation.id.in_(allocation_ids))
            .where(LateFeeCharityAllocation.deleted_at.is_(None))
            .where(LateFeeCharityAllocation.disbursed_at.is_(None))
        )
        allocations = (await self.db.execute(stmt)).scalars().all()
        if not allocations:
            return {"updated_count": 0, "total_amount": 0.0, "status": "already_disbursed"}

        total_amount = sum((Decimal(str(a.late_fee_amount)) for a in allocations), Decimal("0.00"))
        source_id = self._stable_source_id(payment_reference)
        accounting = AccountingService(self.db)
        await accounting.record_charity_disbursement(source_id=source_id, amount=total_amount, reference=payment_reference)

        now = datetime.now(timezone.utc)
        for allocation in allocations:
            allocation.disbursed_at = now
            allocation.receipt_s3 = receipt_s3

        await self.db.commit()
        return {
            "updated_count": len(allocations),
            "total_amount": float(total_amount),
            "status": "disbursed",
        }

    async def get_charity_summary(self, period: str) -> dict[str, object]:
        start_date, end_date = self._period_bounds(period)

        allocated_stmt = (
            select(func.coalesce(func.sum(LateFeeCharityAllocation.late_fee_amount), 0))
            .where(LateFeeCharityAllocation.deleted_at.is_(None))
            .where(func.date(LateFeeCharityAllocation.allocated_at) >= start_date)
            .where(func.date(LateFeeCharityAllocation.allocated_at) <= end_date)
        )
        disbursed_stmt = (
            select(func.coalesce(func.sum(LateFeeCharityAllocation.late_fee_amount), 0))
            .where(LateFeeCharityAllocation.deleted_at.is_(None))
            .where(LateFeeCharityAllocation.disbursed_at.is_not(None))
            .where(func.date(LateFeeCharityAllocation.disbursed_at) >= start_date)
            .where(func.date(LateFeeCharityAllocation.disbursed_at) <= end_date)
        )
        pending_stmt = (
            select(func.coalesce(func.sum(LateFeeCharityAllocation.late_fee_amount), 0))
            .where(LateFeeCharityAllocation.deleted_at.is_(None))
            .where(LateFeeCharityAllocation.disbursed_at.is_(None))
        )

        allocated = Decimal(str((await self.db.execute(allocated_stmt)).scalar_one()))
        disbursed = Decimal(str((await self.db.execute(disbursed_stmt)).scalar_one()))
        pending = Decimal(str((await self.db.execute(pending_stmt)).scalar_one()))

        org_stmt = (
            select(
                CharityOrganization.name,
                func.coalesce(func.sum(LateFeeCharityAllocation.late_fee_amount), 0).label("total"),
            )
            .join(LateFeeCharityAllocation, LateFeeCharityAllocation.charity_org_id == CharityOrganization.id)
            .where(LateFeeCharityAllocation.deleted_at.is_(None))
            .group_by(CharityOrganization.name)
            .order_by(CharityOrganization.name.asc())
        )
        by_org_rows = (await self.db.execute(org_stmt)).all()
        by_org = [{"charity_org": row.name, "total_allocated": float(Decimal(str(row.total)))} for row in by_org_rows]

        return {
            "period": period,
            "allocated": float(allocated),
            "disbursed": float(disbursed),
            "pending": float(pending),
            "by_org": by_org,
        }

    async def validate_charity_routing_ratio(self, period: str) -> dict[str, object]:
        summary = await self.get_charity_summary(period)
        allocated = Decimal(str(summary["allocated"]))
        disbursed = Decimal(str(summary["disbursed"]))
        ratio = Decimal("100.0") if allocated == Decimal("0") else (disbursed / allocated) * Decimal("100")
        summary["disbursed_to_allocated_ratio"] = float(ratio.quantize(Decimal("0.01")))
        return summary

    def _stable_source_id(self, payment_reference: str) -> int:
        digest = sha1(payment_reference.encode("utf-8"), usedforsecurity=False).hexdigest()[:15]
        return int(digest, 16)

    def _period_bounds(self, period: str) -> tuple[date, date]:
        from src.services.accounting_service import AccountingService

        # Reuse existing period parser behavior from AccountingService.
        return AccountingService(self.db)._period_bounds(period)
