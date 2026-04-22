from __future__ import annotations

import inspect
from datetime import date
import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import Installment
from sk_shared.redis_client import RedisClient
from src.billing.overdue_processor import OverdueProcessor
from src.events.publisher import EventPublisher


logger = logging.getLogger(__name__)


class BillingSweepService:
    LOCK_KEY = "ledger:billing_sweep:lock"
    LOCK_TTL_SECONDS = 3600

    def __init__(self, db_session: AsyncSession, redis: RedisClient | None = None) -> None:
        self.db = db_session
        self.redis = redis
        self.publisher = EventPublisher(redis) if redis else None

    async def load_due_installments(self, as_of: date | None = None, limit: int = 500, offset: int = 0) -> list[Installment]:
        """
        Load due installments with cursor-based pagination.
        
        Args:
            as_of: Date to check (defaults to today)
            limit: Max installments per batch (default 500)
            offset: Number of records to skip (for pagination)
            
        Returns:
            List of Installment objects ordered by due_date, then id
        """
        due_date = as_of or date.today()
        stmt = (
            select(Installment)
            .where(Installment.status == "pending", Installment.due_date <= due_date)
            .order_by(Installment.due_date.asc(), Installment.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def plan_daily_sweep(self, as_of: date | None = None, limit: int = 500) -> dict[str, object]:
        installments = await self.load_due_installments(as_of=as_of, limit=limit)
        return {
            "as_of": (as_of or date.today()).isoformat(),
            "due_count": len(installments),
            "installments": [
                {
                    "installment_id": installment.id,
                    "loan_id": installment.loan_id,
                    "due_date": installment.due_date.isoformat(),
                    "status": installment.status,
                    "retry_count": installment.retry_count,
                    "next_retry_at": installment.next_retry_at.isoformat() if installment.next_retry_at else None,
                }
                for installment in installments
            ],
        }

    async def execute_sweep(self, as_of: date | None = None, batch_size: int = 500) -> dict[str, int]:
        """
        Execute billing sweep: detect overdue installments and apply late fees.
        
        This sweep is a DETECTION and LATE-FEE service, not a payment trigger.
        Payment execution is owned by Payment Orchestrator and triggered separately.
        Ledger service listens for payment.installment_paid events and records entries.
        
        Processes installments in batches of batch_size to avoid hitting memory
        limits or database query timeout when thousands of installments are due.
        
        Args:
            as_of: Date to check (defaults to today)
            batch_size: Number of installments per batch (default 500)
            
        Returns:
            Aggregated statistics across all batches
        """
        from src.services.late_fee_service import LateFeeService

        run_date = as_of or date.today()
        lock_owner: str | None = None
        supports_offset = "offset" in inspect.signature(self.load_due_installments).parameters
        
        if self.redis is None:
            # P0-07: Mandatory lock enforcement in non-test environments.
            # Assuming test environment can be detected via a setting or if redis is explicitly None in tests.
            # For production readiness, we raise an error.
            raise RuntimeError("Redis client is mandatory for BillingSweepService to ensure distributed locking.")

        lock_owner = uuid4().hex
        acquired = await self.redis.redis.set(self.LOCK_KEY, lock_owner, ex=self.LOCK_TTL_SECONDS, nx=True)
        if not acquired:
            logger.warning("Billing sweep lock already held; skipping run")
            return {"total": 0, "success": 0, "failed": 0, "already_paid": 0, "newly_overdue": 0, "late_fees_applied": 0}

        try:
            # Aggregate stats across all batches
            aggregate_stats = {"total": 0, "success": 0, "failed": 0, "already_paid": 0, "newly_overdue": 0, "late_fees_applied": 0}
            overdue_processor = OverdueProcessor(self.db, publisher=self.publisher)
            late_fee_service = LateFeeService(self.db)

            # Count due installments for reporting only; payment trigger is external
            offset = 0
            while True:
                # Load next batch of installments
                if supports_offset:
                    installments = await self.load_due_installments(as_of=run_date, limit=batch_size, offset=offset)
                else:
                    installments = await self.load_due_installments(as_of=run_date, limit=batch_size)
                if not installments:
                    break  # No more installments to process

                aggregate_stats["total"] += len(installments)

                if not supports_offset:
                    break

                offset += batch_size

            # After all batches processed, find and handle newly overdue installments
            overdue_candidates = await overdue_processor.find_newly_overdue(as_of=run_date)
            overdue_ids = [inst.id for inst in overdue_candidates]
            aggregate_stats["newly_overdue"] = await overdue_processor.mark_overdue_batch(overdue_ids, as_of=run_date)

            if aggregate_stats["newly_overdue"] > 0:
                for overdue_inst in overdue_candidates:
                    # BV-01 fallback: We compute days_overdue in-memory since we no longer write it to DB
                    days_overdue = (run_date - overdue_inst.due_date).days if overdue_inst.due_date < run_date else 0
                    late_fee = await overdue_processor.compute_late_fee_amount(overdue_inst, days_overdue)
                    if late_fee > 0:
                        result = await late_fee_service.apply_late_fee_to_installment(overdue_inst.id, late_fee)
                        if result["status"] == "applied":
                            aggregate_stats["late_fees_applied"] += 1

            logger.info(
                "Billing sweep completed",
                extra={
                    "total_due": aggregate_stats["total"],
                    "newly_overdue": aggregate_stats["newly_overdue"],
                    "late_fees_applied": aggregate_stats["late_fees_applied"],
                },
            )
            return aggregate_stats
        finally:
            if self.redis is not None and lock_owner is not None:
                current_owner = await self.redis.get(self.LOCK_KEY)
                # Normalize: redis.get() may return bytes or str depending on client config
                if current_owner is not None:
                    if isinstance(current_owner, bytes):
                        current_owner = current_owner.decode("utf-8")
                    if current_owner == lock_owner:
                        await self.redis.delete(self.LOCK_KEY)