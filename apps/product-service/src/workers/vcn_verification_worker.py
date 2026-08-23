import asyncio
import json
import logging
import signal
from datetime import datetime, timezone
from uuid import UUID

from opentelemetry import trace
from sqlalchemy import select

from sk_shared.constants import QueueName
from sk_shared.database import SessionLocal
from sk_shared.events import (
    EVENT_ORDER_PURCHASE_CONFIRMED,
    build_event_envelope,
    event_channel,
)
from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue
from sk_shared.redis_client import get_redis_client, RedisClient
from src.config import settings
from src.services.checkout.vcn_verifier import VcnVerifier
from src.middleware.metrics import VCN_VERIFICATION_TIMEOUT

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("product-service.worker.vcn-verification")

class VcnVerificationWorker:
    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis
        self.running = True
        self.verifier = VcnVerifier(redis)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: setattr(self, "running", False))
        except NotImplementedError:
            pass

        logger.info("VcnVerificationWorker started, consuming %s", QueueName.VCN_VERIFICATION)

        while self.running:
            job = await self.redis.redis.brpop(QueueName.VCN_VERIFICATION, timeout=5)
            if job is None:
                continue

            try:
                payload = json.loads(job[1].decode("utf-8"))
                await self._process_job(payload)
            except Exception as e:
                logger.error("Error processing VCN verification job: %s", e)

    async def _process_job(self, payload: dict) -> None:
        with tracer.start_as_current_span(
            "vcn_verification_worker.process",
            attributes={
                "execution_id": str(payload.get("execution_id", "")),
                "correlation_id": str(payload.get("correlation_id", "")),
            },
        ):
            execution_id = payload.get("execution_id")
            vcn_id = payload.get("vcn_id")
            payload.get("order_id")
            correlation_id = payload.get("correlation_id")

            if not execution_id or not vcn_id:
                logger.error("Invalid payload for VCN verification: %s", payload)
                return

            async with SessionLocal() as db:
                execution = await db.scalar(
                    select(PurchaseExecution).where(PurchaseExecution.uuid == UUID(execution_id))
                )
                if not execution:
                    logger.error("PurchaseExecution %s not found", execution_id)
                    return

                if execution.status != "pending_verification":
                    logger.warning("Execution %s is in state %s, skipping verification", execution_id, execution.status)
                    return

                logger.info("Verifying charge for execution %s, vcn %s", execution_id, vcn_id)

                # Use the verifier to poll for charge confirmation
                verified = await self.verifier.verify_charge(vcn_id)

                if verified:
                    logger.info("Charge verified for execution %s", execution_id)
                    execution.status = "succeeded"
                    execution.step_reached = "order_confirmed"
                    execution.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    
                    # Update merchant success rate
                    from sk_shared.models.order import Order
                    from sk_shared.models.product import Product
                    merchant_id = await db.scalar(select(Product.merchant_id).join(Order, Order.product_id == Product.id).where(Order.id == execution.order_id))
                    if merchant_id:
                        from src.repositories.merchant_repository import MerchantRepository
                        await MerchantRepository(db).recalculate_success_rate(merchant_id)

                    await db.commit()

                    # Publish Success Event
                    envelope = build_event_envelope(
                        event=EVENT_ORDER_PURCHASE_CONFIRMED,
                        source_service="product-service",
                        correlation_id=correlation_id,
                        payload={
                            "order_id": execution.order_id,
                            "vcn_id": execution.vcn_id,
                            "merchant_order_id": execution.merchant_order_id,
                        },
                    )
                    await self.redis.publish(event_channel(EVENT_ORDER_PURCHASE_CONFIRMED), envelope.to_json())
                else:
                    logger.warning("Verification timed out for vcn %s", vcn_id)
                    VCN_VERIFICATION_TIMEOUT.labels(vcn_id=str(vcn_id)).inc()

                    # Escalation to HITL if it takes too long
                    if settings.FEATURE_HITL_ESCALATION:
                        hitl = HitlQueue(
                            order_id=execution.order_id,
                            execution_id=execution.id,
                            status="pending",
                            failure_reason=f"VCN verification timed out for VCN {vcn_id}",
                        )
                        db.add(hitl)
                        execution.status = "hitl_escalated"
                        await db.commit()
                    else:
                        # Move back to queue or mark as failed?
                        # For now, we'll mark as failed to avoid infinite loops if HITL is off.
                        execution.status = "failed"
                        execution.failure_type = "verification_timeout"
                        execution.error_detail = f"VCN verification timed out for VCN {vcn_id}"
                        execution.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                        
                        # Update merchant success rate
                        from sk_shared.models.order import Order
                        from sk_shared.models.product import Product
                        merchant_id = await db.scalar(select(Product.merchant_id).join(Order, Order.product_id == Product.id).where(Order.id == execution.order_id))
                        if merchant_id:
                            from src.repositories.merchant_repository import MerchantRepository
                            await MerchantRepository(db).recalculate_success_rate(merchant_id)

                        await db.commit()

                        # Publish Failure Event for Rollback
                        envelope = build_event_envelope(
                            event="order.purchase_failed",
                            source_service="product-service",
                            correlation_id=correlation_id,
                            payload={
                                "order_id": execution.order_id,
                                "vcn_id": execution.vcn_id,
                                "reason": "vcn_verification_timeout",
                            },
                        )
                        await self.redis.publish("sk:events:order.purchase_failed", envelope.to_json())

async def _amain() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    worker = VcnVerificationWorker(redis)
    try:
        await worker.run()
    finally:
        await redis.close()
        logger.info("VcnVerificationWorker shut down cleanly")

def main() -> None:
    asyncio.run(_amain())

if __name__ == "__main__":
    main()
