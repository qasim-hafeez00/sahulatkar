from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.http_client import request as internal_http_request
from src.middleware.metrics import CHECKOUT_STEP_DURATION
from src.services.s3_service import S3Service
from src.services.checkout.form_filler import CheckoutFormFiller
from src.services.checkout.vcn_verifier import VcnVerifier

from sk_shared.constants import QueueName
from sk_shared.events import (
    build_event_envelope,
    event_channel,
)
from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.order import Order
from sk_shared.models.payment import VirtualCard
from sk_shared.models.product import Product
from sk_shared.redis_client import RedisClient

class CheckoutAgentService:
    """Orchestrator for autonomous checkout operations.
    
    DESIGN-01: Decomposed monolith into cleaner, modular structure.
    Coordinates between database, redis, s3, form filler and verification.
    """
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self.db = db
        self.redis = redis
        self.s3_service = S3Service()
        self.form_filler = CheckoutFormFiller(redis)
        self.verifier = VcnVerifier(redis)

    async def queue_job(
        self,
        *,
        order_id: int,
        vcn_id: int,
        correlation_id: str | None = None,
        force_failure: bool = False,
    ) -> PurchaseExecution:
        """Enqueue a new checkout job into the FIFO worker queue.

        The job payload intentionally never carries PAN/CVV — card data must never
        sit in a Redis queue or DLQ in plaintext. The worker fetches it just-in-time
        from Payment Orchestrator's internal decrypt endpoint (see
        `_fetch_vcn_credentials`) right before it's needed.
        """
        existing = await self.db.scalar(
            select(PurchaseExecution)
            .where(
                PurchaseExecution.order_id == order_id,
                PurchaseExecution.vcn_id == vcn_id,
                PurchaseExecution.status.in_(["queued", "running", "pending_verification"]),
            )
            .order_by(PurchaseExecution.created_at.desc())
        )
        if existing is not None:
            return existing

        now = datetime.now(timezone.utc)
        execution = PurchaseExecution(
            order_id=order_id,
            vcn_id=vcn_id,
            status="queued",
            step_reached="queued",
            # queued_at is TIMESTAMP WITHOUT TIME ZONE (partition-adjacent
            # column, same convention as delivery's TrackingEvent.event_time)
            # — an aware datetime here 500s the insert outright
            # ("can't subtract offset-naive and offset-aware datetimes").
            queued_at=now.replace(tzinfo=None),
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)

        payload = {
            "execution_id": str(execution.uuid),
            "order_id": order_id,
            "vcn_id": vcn_id,
            "correlation_id": correlation_id,
            "force_failure": force_failure,
        }
        # BUG-02 FIX: Use lpush for FIFO behavior.
        await self.redis.lpush(QueueName.CHECKOUT, json.dumps(payload))
        return execution

    async def _fetch_vcn_credentials(self, order_id: int) -> dict:
        """Fetch plaintext PAN/CVV/expiry for an order's VCN, just-in-time.

        Calls Payment Orchestrator's internal-only decrypt endpoint instead of
        ever persisting card data in Redis queues/DLQ or the admin API.
        """
        response = await internal_http_request(
            "GET",
            f"{settings.PAYMENT_ORCHESTRATOR_URL}/api/v1/payments/internal/vcn/{order_id}/decrypt",
            headers={"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN},
        )
        response.raise_for_status()
        return response.json()

    async def process_job(self, payload: dict) -> None:
        """Main entry point for background workers to execute a checkout job."""
        execution = await self._load_execution(payload["execution_id"])
        if not execution or execution.status in {"succeeded", "failed", "hitl_escalated", "cancelled"}:
            return

        # Initialize attempt
        execution.attempt_number += 1
        execution.worker_id = socket.gethostname()
        await self.db.commit()

        # Load dependencies
        order = await self.db.get(Order, execution.order_id)
        if not order or not order.product_id:
            await self._mark_failed(execution, "unknown", "Order or product missing.")
            return

        product = await self.db.get(Product, order.product_id)
        vcn = await self.db.get(VirtualCard, execution.vcn_id)
        if not product or not vcn:
            await self._mark_failed(execution, "unknown", "Product or VCN missing.")
            return

        started_at = datetime.now(timezone.utc)
        execution.status = "running"
        # started_at/completed_at are TIMESTAMP WITHOUT TIME ZONE columns
        # (same convention as queued_at above) — keep `started_at` itself
        # aware for the duration_ms subtraction below, store the naive form.
        execution.started_at = started_at.replace(tzinfo=None)
        await self.db.commit()

        # Support for regression testing forced failures
        if payload.get("force_failure"):
            await self._mark_failed(execution, "checkout_changed", "FORCED_FAILURE_FOR_TEST")
            return

        try:
            step_clock = time.perf_counter()

            async def emit_step(step: str) -> None:
                nonlocal step_clock
                now = time.perf_counter()
                CHECKOUT_STEP_DURATION.labels(step=step).observe(max(now - step_clock, 0.0))
                step_clock = now
                execution.step_reached = step
                await self.db.commit()

            self.form_filler.set_step_callback(emit_step)

            # Card data is never carried in the queue payload — fetch it
            # just-in-time from Payment Orchestrator's internal decrypt endpoint.
            credentials = await self._fetch_vcn_credentials(execution.order_id)

            # Execute Playwright automation logic via FormFiller
            # BUG-01 FIX: order is passed explicitly.
            result = await self.form_filler.run_checkout(
                product=product,
                order=order,
                pan=credentials["pan"],
                cvv=credentials["cvv"],
                exp_month=credentials["expiry_month"],
                exp_year=credentials["expiry_year"],
                attempt_number=execution.attempt_number,
                execution_uuid=str(execution.uuid),
            )

            # Update status upon visual confirmation
            execution.status = "succeeded"
            execution.step_reached = "order_confirmed"
            execution.merchant_order_id = result.get("merchant_order_id")
            execution.merchant_order_url = result.get("merchant_order_url")
            completed_at = datetime.now(timezone.utc)
            execution.completed_at = completed_at.replace(tzinfo=None)
            execution.duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            await self.db.commit()

            # GAP-21: VCN Verification (Decoupled)
            # We no longer block the checkout worker slot with an inline poll.
            # Instead, we mark as pending and delegate to vcn-verifier worker.
            execution.status = "pending_verification"
            execution.step_reached = "pending_verification"
            await self.db.commit()

            verification_payload = {
                "execution_id": str(execution.uuid),
                "order_id": execution.order_id,
                "vcn_id": execution.vcn_id,
                "correlation_id": payload.get("correlation_id"),
            }
            await self.redis.lpush(QueueName.VCN_VERIFICATION, json.dumps(verification_payload))
            
            # BUG-03 FIX: Upload receipt screenshot from bytes returned by FormFiller
            receipt_bytes = result.get("receipt_screenshot")
            if receipt_bytes:
                await self._upload_screenshot(execution, receipt_bytes, "success_receipt")
            
            return

        except Exception as e:
            # Handle specific failures or generic errors
            error_msg = str(e)
            failure_type = "checkout_changed"
            if "OUT_OF_STOCK" in error_msg:
                failure_type = "out_of_stock"
            elif "PRICE_MISMATCH" in error_msg:
                failure_type = "price_mismatch"
            elif "UNCERTAIN_CHECKOUT_OUTCOME" in error_msg:
                failure_type = "checkout_uncertain"
            
            if failure_type == "checkout_uncertain":
                execution.status = "pending_verification"
                execution.step_reached = "checkout_uncertain"
                await self.db.commit()
                await self.redis.publish("sk:events:checkout.uncertain", json.dumps({"execution_id": str(execution.uuid), "order_id": execution.order_id}))
            else:
                await self._mark_failed(execution, failure_type, error_msg)
        finally:
            self.form_filler.set_step_callback(None)

    async def cancel_job(self, job_uuid: UUID):
        """Cancel a queued or running job."""
        execution = await self.db.scalar(select(PurchaseExecution).where(PurchaseExecution.uuid == job_uuid))
        if not execution or execution.status in {"succeeded", "failed", "hitl_escalated", "cancelled"}:
            return

        execution.status = "cancelled"
        execution.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.commit()

        # Remove from queue if present
        try:
            items = await self.redis.redis.lrange(QueueName.CHECKOUT, 0, -1)
            for item in items:
                payload_raw = item.decode("utf-8") if isinstance(item, bytes) else str(item)
                try:
                    obj = json.loads(payload_raw)
                    if str(obj.get("execution_id")) == str(job_uuid):
                        await self.redis.redis.lrem(QueueName.CHECKOUT, 1, item)
                except Exception:
                    continue
        except Exception:
            pass

        # Publish void event for VCN cleanup
        envelope = build_event_envelope(
            event="vcn.void",
            source_service="product-service",
            correlation_id=str(job_uuid),
            payload={
                "execution_id": str(execution.uuid),
                "order_id": execution.order_id,
                "vcn_id": execution.vcn_id,
                "reason": "checkout_cancelled",
            },
        )
        await self.redis.publish(event_channel("vcn.void"), envelope.to_json())

    async def _load_execution(self, execution_uuid: str) -> PurchaseExecution | None:
        try:
            uid = UUID(execution_uuid)
        except Exception:
            return None
        return await self.db.scalar(select(PurchaseExecution).where(PurchaseExecution.uuid == uid))

    async def _mark_failed(self, execution: PurchaseExecution, failure_type: str, error_detail: str) -> None:
        execution.status = "failed"
        execution.failure_type = failure_type
        execution.error_detail = error_detail
        execution.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.commit()

        if settings.FEATURE_HITL_ESCALATION:
            hitl = HitlQueue(
                order_id=execution.order_id,
                execution_id=execution.id,
                status="pending",
                failure_reason=f"{failure_type}: {error_detail}",
            )
            self.db.add(hitl)
            execution.status = "hitl_escalated"
            await self.db.commit()

    async def _upload_screenshot(self, execution: PurchaseExecution, data: bytes, step: str):
        try:
            key = f"screenshots/{execution.uuid}/{step}.jpg"
            await self.s3_service.upload_bytes(data, key, content_type="image/jpeg")
            if step == "success_receipt":
                execution.receipt_screenshot_s3 = key
            else:
                execution.screenshot_s3 = key
            await self.db.commit()
        except Exception:
            pass
    async def requeue_execution(self, execution: PurchaseExecution) -> None:
        """Re-enqueue an existing failed or stalled execution."""
        execution.status = "queued"
        execution.step_reached = "queued"
        execution.started_at = None
        execution.completed_at = None
        execution.failure_type = None
        execution.error_detail = None
        await self.db.commit()

        payload = {
            "execution_id": str(execution.uuid),
            "order_id": execution.order_id,
            "vcn_id": execution.vcn_id,
        }
        await self.redis.lpush(QueueName.CHECKOUT, json.dumps(payload))
