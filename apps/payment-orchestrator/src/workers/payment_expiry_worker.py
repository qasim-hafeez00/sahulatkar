import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from src.core.database import SessionLocal
from src.models.payment_workflow import PaymentWorkflow
from src.orchestration.payment_orchestrator import PaymentOrchestrator
from src.state.payment_workflow import PaymentStatus

logger = logging.getLogger(__name__)


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
        async with SessionLocal() as db:
            orchestrator = PaymentOrchestrator(db)
            now = datetime.now(timezone.utc)
            
            result = await db.execute(
                select(PaymentWorkflow)
                .where(PaymentWorkflow.status == PaymentStatus.INITIATED)
                .where(PaymentWorkflow.session_expires_at < now)
            )
            expired_workflows = result.scalars().all()
            
            for workflow in expired_workflows:
                try:
                    await orchestrator.expire_session(workflow.id)
                    logger.info(f"Expired payment session {workflow.id} for order {workflow.order_id}")
                except Exception as e:
                    logger.error(f"Failed to expire session {workflow.id}: {e}")
            
            if expired_workflows:
                await db.commit()

    def stop(self):
        self.is_running = False


if __name__ == "__main__":
    worker = PaymentSessionExpiryWorker()
    asyncio.run(worker.run())
