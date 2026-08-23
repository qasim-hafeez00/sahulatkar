from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import logging
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.ledger import CharityOrganization, LateFeeCharityAllocation
from src.config import settings
from src.services.accounting_service import AccountingService
from src.accounting.accounts import ACCOUNT_CODES
from src.core.period_utils import get_period_bounds
from src.core.readonly_guard import readonly_guard
from sk_shared.redis_client import RedisClient


logger = logging.getLogger(__name__)


class CharityService:
    # P1: distributed lock guarding process_charity_allocation, mirroring
    # BillingSweepService's lock — without it, two concurrent disbursement
    # runs (e.g. an admin click racing the scheduled sweep) can both read the
    # same pending allocations and both post a charity disbursement GL entry
    # for them, double-disbursing the same money.
    LOCK_KEY = "ledger:charity_disbursement:lock"
    LOCK_TTL_SECONDS = 600

    def __init__(self, db_session: AsyncSession, redis: RedisClient | None = None) -> None:
        self.db = db_session
        self.redis = redis

    @readonly_guard
    async def get_pending_disbursements(self, min_age_days: int | None = None) -> list[LateFeeCharityAllocation]:
        # LS-BL-04: Use config-driven min_age_days instead of hardcoded value
        effective_min_age = min_age_days if min_age_days is not None else settings.charity_disbursement_min_age_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=effective_min_age)
        stmt = (
            select(LateFeeCharityAllocation)
            .where(LateFeeCharityAllocation.deleted_at.is_(None))
            .where(LateFeeCharityAllocation.disbursed_at.is_(None))
            .where(LateFeeCharityAllocation.allocated_at <= cutoff)
            .order_by(LateFeeCharityAllocation.allocated_at.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    @readonly_guard
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
        
        # ACC-05: Balance pre-check before disbursement
        accounting = AccountingService(self.db, redis=self.redis)
        charity_balance = await accounting.get_account_balance(ACCOUNT_CODES["charity_payable"])
        if Decimal(str(charity_balance["balance"])) < total_amount:
            raise ValueError(f"Insufficient funds in charity account: {charity_balance['balance']} < {total_amount}")

        source_id = self._stable_source_id(payment_reference)
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

    @readonly_guard
    async def get_charity_summary(self, period: str) -> dict[str, object]:
        start_date, end_date = get_period_bounds(period)

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
        from src.core.metrics import SHARIAH_COMPLIANCE_RATIO
        from src.events.publisher import EventPublisher
        
        summary = await self.get_charity_summary(period)
        allocated = Decimal(str(summary["allocated"]))
        disbursed = Decimal(str(summary["disbursed"]))
        ratio = Decimal("100.0") if allocated == Decimal("0") else (disbursed / allocated) * Decimal("100")
        ratio_float = float(ratio.quantize(Decimal("0.01")))
        
        summary["disbursed_to_allocated_ratio"] = ratio_float
        SHARIAH_COMPLIANCE_RATIO.set(ratio_float / 100.0)
        
        # P2-07: Shariah Alerting
        if ratio < Decimal("100.0"):
            if self.redis:
                publisher = EventPublisher(self.redis)
                await publisher.publish_shariah_violation(
                    reason="Charity routing ratio fell below 100%",
                    details={"period": period, "ratio": ratio_float, "allocated": float(allocated), "disbursed": float(disbursed)}
                )
                
        return summary

    def _stable_source_id(self, payment_reference: str) -> int:
        digest = sha256(payment_reference.encode("utf-8")).hexdigest()[:15]
        return int(digest, 16)

    async def process_charity_allocation(self, payment_reference: str | None = None, receipt_s3: str | None = None) -> dict[str, object]:
        """
        LS-CRIT-03: Full auto-disbursement pipeline for charity allocations.

        1. Fetches all undisbursed LateFeeCharityAllocation records older than
           settings.charity_disbursement_min_age_days.
        2. Checks Shariah nisab threshold — only disburse if total >= nisab.
        3. Verifies charity_payable GL balance covers the total.
        4. Records the charity disbursement GL entry.
        5. Marks all allocations as disbursed.

        Guarded by a Redis NX lock (mirroring BillingSweepService) so two
        concurrent runs can't both read the same pending allocations and both
        post a disbursement GL entry for them.
        """
        if self.redis is None:
            raise RuntimeError("Redis client is mandatory for CharityService to ensure distributed locking.")

        lock_owner = uuid4().hex
        acquired = await self.redis.redis.set(self.LOCK_KEY, lock_owner, ex=self.LOCK_TTL_SECONDS, nx=True)
        if not acquired:
            logger.warning("Charity disbursement lock already held; skipping run")
            return {
                "status": "locked",
                "disbursed_count": 0,
                "total_amount": 0.0,
                "message": "Another charity disbursement run is already in progress.",
            }

        try:
            return await self._process_charity_allocation_locked(payment_reference, receipt_s3)
        finally:
            current_owner = await self.redis.get(self.LOCK_KEY)
            if isinstance(current_owner, bytes):
                current_owner = current_owner.decode("utf-8")
            if current_owner == lock_owner:
                await self.redis.delete(self.LOCK_KEY)

    async def _process_charity_allocation_locked(
        self, payment_reference: str | None, receipt_s3: str | None
    ) -> dict[str, object]:
        pending = await self.get_pending_disbursements()
        if not pending:
            return {
                "status": "no_pending",
                "disbursed_count": 0,
                "total_amount": 0.0,
                "message": "No pending charity allocations meeting minimum age threshold.",
            }

        total_amount = sum((Decimal(str(a.late_fee_amount)) for a in pending), Decimal("0.00"))

        # LS-BL-04: Shariah nisab check — configurable via settings
        nisab = Decimal(str(settings.shariah_nisab_pkr))
        if total_amount < nisab:
            logger.info(
                "Charity allocation below nisab threshold; skipping disbursement",
                extra={"total_amount": float(total_amount), "nisab": float(nisab)},
            )
            return {
                "status": "below_nisab",
                "disbursed_count": 0,
                "total_amount": float(total_amount),
                "nisab_threshold": float(nisab),
                "message": "Total pending charity is below the Shariah nisab threshold.",
            }

        # Balance pre-check
        accounting = AccountingService(self.db, redis=self.redis)
        charity_balance = await accounting.get_account_balance(ACCOUNT_CODES["charity_payable"])
        if Decimal(str(charity_balance["balance"])) < total_amount:
            raise ValueError(
                f"Insufficient funds in charity_payable: "
                f"{charity_balance['balance']} < {total_amount}"
            )

        # Build a stable reference for idempotency
        ref = payment_reference or f"AUTO-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        source_id = self._stable_source_id(ref)
        await accounting.record_charity_disbursement(
            source_id=source_id,
            amount=total_amount,
            reference=ref,
        )

        # Mark allocations as disbursed
        now = datetime.now(timezone.utc)
        for allocation in pending:
            allocation.disbursed_at = now
            if receipt_s3:
                allocation.receipt_s3 = receipt_s3

        await self.db.commit()

        logger.info(
            "Charity auto-disbursement completed",
            extra={"total_amount": float(total_amount), "count": len(pending), "reference": ref},
        )
        return {
            "status": "disbursed",
            "disbursed_count": len(pending),
            "total_amount": float(total_amount),
            "reference": ref,
        }

