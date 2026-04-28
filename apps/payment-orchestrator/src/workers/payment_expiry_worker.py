import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from src.core.database import SessionLocal
from src.models.payment_workflow import PaymentWorkflow
from src.orchestration.payment_orchestrator import PaymentOrchestrator
from src.state.payment_workflow import PaymentStatus

logger = logging.getLogger(__name__)

# PO-BL-08: Concurrency and batch config
_EXPIRY_BATCH_SIZE = 100
_EXPIRY_CONCURRENCY = 10


class PaymentSessionExpiryWorker:
    def __init__(self):
        self.is_running = True

    async def run(self):
        logger.info("Starting PaymentSessionExpiryWorker")
        while self.is_running:
            try:
                await self.sweep_expired_sessions()
            except Exception as e:
                logger.error(f"Error in PaymentSessionExpiryWorker: {e}")
            await asyncio.sleep(60)  # Check every minute

    async def sweep_expired_sessions(self):
        """
        PO-BL-08: Process expired sessions in batches with semaphore-controlled
        concurrency to avoid blocking under high load (thousands of expirations).
        """
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)

            result = await db.execute(
                select(PaymentWorkflow)
                .where(PaymentWorkflow.status.in_([PaymentStatus.INITIATED, PaymentStatus.PENDING]))
                .where(PaymentWorkflow.session_expires_at < now)
                .limit(_EXPIRY_BATCH_SIZE)
            )
            expired_workflows = result.scalars().all()

            if not expired_workflows:
                return

            # PO-BL-08: Use semaphore to cap concurrent expiry mutations
            sem = asyncio.Semaphore(_EXPIRY_CONCURRENCY)

            async def _expire_one(wf_id: int):
                async with sem:
                    async with SessionLocal() as inner_db:
                        orchestrator = PaymentOrchestrator(inner_db)
                        try:
                            await orchestrator.expire_session(wf_id)
                            await inner_db.commit()
                            logger.info(f"Expired payment session {wf_id}")
                        except Exception as e:
                            logger.error(f"Failed to expire session {wf_id}: {e}")

            await asyncio.gather(*[_expire_one(wf.id) for wf in expired_workflows])
            logger.info(f"PaymentSessionExpiryWorker: expired {len(expired_workflows)} sessions in this batch")

    def stop(self):
        self.is_running = False


if __name__ == "__main__":
    worker = PaymentSessionExpiryWorker()
    asyncio.run(worker.run())

