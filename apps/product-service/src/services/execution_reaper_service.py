from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue

from src.config import settings


class ExecutionReaperService:
    """Reaps `PurchaseExecution` rows stuck at status='running' past a
    reasonable timeout.

    HIGH-02: a checkout-worker process that crashes or is killed mid-job
    (OOM, deploy, host failure) leaves its execution row at 'running'
    forever -- `process_job()` in `CheckoutAgentService` only ever writes a
    terminal status from inside its own try/except, so a hard process kill
    between two `await self.db.commit()` calls in `emit_step` never gets a
    chance to run that cleanup. The admin retry endpoint
    (`POST /admin/executions/{uuid}/retry`) explicitly no-ops on 'running',
    so without this there was no way to recover such a row short of a manual
    DB UPDATE.

    Shared by two call sites so both agree on exactly what "stuck" means:
      - `ExecutionReaperWorker`'s scheduled sweep (src/workers/
        execution_reaper_worker.py), consistent with this codebase's other
        scheduled-sweep workers (PriceStalenessWorker, ProhibitedCatalogWorker).
      - The admin retry endpoint's just-in-time check, so an admin
        investigating a visibly-stuck execution doesn't have to wait for the
        next sweep interval to recover it.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def is_stuck(execution: PurchaseExecution, *, now: datetime | None = None) -> bool:
        """True if `execution` is 'running' and has been for longer than
        CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS.

        An execution with no `started_at` recorded yet (e.g. seeded directly
        in a test, or genuinely just transitioned to 'running' this instant)
        is never considered stuck -- there's no elapsed time to judge it by.
        """
        if execution.status != "running" or execution.started_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        started_at = execution.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        elapsed = (now - started_at).total_seconds()
        return elapsed > settings.CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS

    async def reap(self, execution: PurchaseExecution) -> None:
        """Move a single stuck execution to a terminal state and commit.

        Mirrors `CheckoutAgentService._mark_failed`'s convention: base state
        is 'failed' with a failure_type/error_detail, escalated to
        'hitl_escalated' (with a HitlQueue entry for manual review of
        whether the merchant-side purchase actually completed before this
        worker died) when HITL escalation is enabled. Either terminal status
        is retryable via the admin endpoint.
        """
        execution.status = "failed"
        execution.failure_type = "worker_timeout"
        execution.error_detail = (
            "Reaped by ExecutionReaperService: execution was stuck at "
            f"'running' for over {settings.CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS}s with no "
            "terminal status ever written -- the owning checkout-worker "
            "process likely crashed or was killed mid-purchase."
        )
        execution.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if settings.FEATURE_HITL_ESCALATION:
            self.db.add(
                HitlQueue(
                    order_id=execution.order_id,
                    execution_id=execution.id,
                    status="pending",
                    failure_reason=(
                        f"Checkout execution {execution.uuid} timed out at 'running' "
                        "(worker crash/kill) -- verify merchant-side purchase state "
                        "before retrying or refunding."
                    ),
                )
            )
            execution.status = "hitl_escalated"

        await self.db.commit()

    async def reap_all_stuck(self) -> list[PurchaseExecution]:
        """Find and reap every currently-stuck execution. Returns the rows
        that were reaped (already committed)."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS)
        result = await self.db.execute(
            select(PurchaseExecution).where(
                PurchaseExecution.status == "running",
                PurchaseExecution.started_at.is_not(None),
                PurchaseExecution.started_at < cutoff.replace(tzinfo=None),
            )
        )
        stuck = list(result.scalars())
        for execution in stuck:
            await self.reap(execution)
        return stuck
