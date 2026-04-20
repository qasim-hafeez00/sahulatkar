from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.services.s3_service import S3Service
from src.services.checkout.form_filler import CheckoutFormFiller
from src.services.checkout.vcn_verifier import VcnVerifier

from sk_shared.constants import QueueName
from sk_shared.events import (
    EVENT_ORDER_PURCHASE_CONFIRMED,
    build_event_envelope,
    event_channel,
)
from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.order import Order
from sk_shared.models.payment import VirtualCard
from sk_shared.models.product import Product
from sk_shared.redis_client import RedisClient
from sk_shared.security import SecretService

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
        """Enqueue a new checkout job into the FIFO worker queue."""
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
            queued_at=now,
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
        execution.started_at = started_at
        await self.db.commit()

        # Support for regression testing forced failures
        if payload.get("force_failure"):
            await self._mark_failed(execution, "checkout_changed", "FORCED_FAILURE_FOR_TEST")
            return

        try:
            # Decrypt credentials
            encryption_key = settings.FERNET_KEY.encode()
            pan = SecretService.decrypt_secret(vcn.encrypted_pan, encryption_key).decode() if vcn.encrypted_pan else ""
            cvv = SecretService.decrypt_secret(vcn.encrypted_cvv, encryption_key).decode() if vcn.encrypted_cvv else ""

            # Execute Playwright automation logic via FormFiller
            # BUG-01 FIX: order is passed explicitly.
            result = await self.form_filler.run_checkout(
                product=product,
                order=order,
                pan=pan,
                cvv=cvv,
                attempt_number=execution.attempt_number,
                execution_uuid=str(execution.uuid),
            )

            # Update status upon visual confirmation
            execution.status = "succeeded"
            execution.step_reached = "order_confirmed"
            execution.merchant_order_id = result.get("merchant_order_id")
            execution.merchant_order_url = result.get("merchant_order_url")
            execution.completed_at = datetime.now(timezone.utc)
            execution.duration_ms = int((execution.completed_at - started_at).total_seconds() * 1000)
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

    async def cancel_job(self, job_uuid: UUID):
        """Cancel a queued or running job."""
        execution = await self.db.scalar(select(PurchaseExecution).where(PurchaseExecution.uuid == job_uuid))
        if not execution or execution.status in {"succeeded", "failed", "hitl_escalated", "cancelled"}:
            return

        execution.status = "cancelled"
        execution.completed_at = datetime.now(timezone.utc)
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
        execution.completed_at = datetime.now(timezone.utc)
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
