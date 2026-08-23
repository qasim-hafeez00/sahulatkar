"""
Refund Orchestrator.

Orchestrates the lifecycle of a refund, including recording state changes
and calling the appropriate gateway adapter.
"""
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.events import build_event_envelope
from src.models.refund_workflow import RefundWorkflow, RefundStatus
from src.models.outbox import OutboxEvent
from src.adapters.factory import GatewayAdapterFactory
from src.config import settings

logger = logging.getLogger(__name__)


class RefundOrchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def initiate_refund(
        self,
        *,
        payment_workflow_id: int,
        order_id: int,
        user_id: int,
        amount_pkr: Decimal,
        reason: str,
        refund_reference: str,
        gateway: str,
        gateway_txn_id: str,
    ) -> RefundWorkflow:
        """
        Initiate a refund workflow and call the gateway adapter.

        gateway_txn_id must be the original successful transaction's gateway
        reference, supplied directly by the caller. This used to be derived
        by looking up PaymentWorkflow.gateway_session_id via
        payment_workflow_id — but PaymentWorkflow rows only exist for
        payments made through this service's own (production-unreachable,
        see src/api/v1/payments.py) down-payment endpoint. A refund for a
        payment Gateway itself processed (the only production-reachable
        path — see src/workers/payment_initiate_consumer.py) has no
        PaymentWorkflow at all, so payment_workflow_id is always 0 there and
        this always failed with ORIGINAL_TRANSACTION_NOT_FOUND. Every real
        caller already has the gateway_txn_id from the PaymentTransaction row
        it looked up, so take it directly instead of re-deriving it.
        payment_workflow_id is kept only for the RefundWorkflow audit-trail FK.
        """
        # 1. Idempotency check
        existing = await self.db.scalar(
            select(RefundWorkflow).where(RefundWorkflow.refund_reference == refund_reference)
        )
        if existing:
            return existing

        # 2. Record initiation
        refund = RefundWorkflow(
            original_payment_workflow_id=payment_workflow_id,
            order_id=order_id,
            user_id=user_id,
            refund_reference=refund_reference,
            amount_pkr=amount_pkr,
            reason=reason,
            status=RefundStatus.INITIATED,
            gateway=gateway,
        )
        self.db.add(refund)
        await self.db.flush()

        if not gateway_txn_id:
            logger.error(
                "No gateway_txn_id supplied for refund — cannot call gateway",
                extra={"payment_workflow_id": payment_workflow_id, "refund_reference": refund_reference}
            )
            refund.status = RefundStatus.FAILED
            refund.failure_reason = "ORIGINAL_TRANSACTION_NOT_FOUND"
            await self._queue_event("payment.refund_failed", {
                "refund_id": refund.id,
                "order_id": order_id,
                "reason": refund.failure_reason
            })
            return refund

        # 3. Call gateway via adapter
        adapter = GatewayAdapterFactory.get(gateway, settings)
        try:
            result = await adapter.refund(
                gateway_txn_id=gateway_txn_id,
                amount_pkr=amount_pkr,
                reason=reason
            )
            
            refund.gateway_refund_id = result.get("gateway_refund_id")
            
            # If the gateway confirms it immediately (like SafePay)
            if result.get("status") == "success":
                refund.status = RefundStatus.SETTLED
                refund.settled_at = datetime.now(timezone.utc)
                event_name = "payment.refund_settled"
            else:
                refund.status = RefundStatus.PENDING
                event_name = "payment.refund_initiated"

            await self._queue_event(
                event_name,
                {
                    "refund_id": refund.id,
                    "order_id": refund.order_id,
                    "amount_pkr": str(refund.amount_pkr),
                    "gateway_refund_id": refund.gateway_refund_id,
                    "reason": refund.reason,
                }
            )

        except Exception as exc:
            logger.error(
                "Gateway refund call failed",
                extra={"gateway": gateway, "refund_reference": refund_reference, "error": str(exc)}
            )
            refund.status = RefundStatus.FAILED
            refund.failure_reason = str(exc)
            refund.failed_at = datetime.now(timezone.utc)
            
            await self._queue_event("payment.refund_failed", {
                "refund_id": refund.id,
                "order_id": order_id,
                "reason": refund.failure_reason
            })

        return refund

    async def settle_refund(self, refund_id: int, gateway_refund_id: str) -> None:
        """
        Settle a pending refund (e.g. from webhook).
        """
        refund = await self.db.get(RefundWorkflow, refund_id)
        if not refund:
            return

        if refund.status == RefundStatus.SETTLED:
            return

        refund.status = RefundStatus.SETTLED
        refund.gateway_refund_id = gateway_refund_id
        refund.settled_at = datetime.now(timezone.utc)
        
        await self._queue_event(
            "payment.refund_settled",
            {
                "refund_id": refund.id,
                "order_id": refund.order_id,
                "gateway_refund_id": gateway_refund_id,
            }
        )

    async def _queue_event(self, event_name: str, payload: dict):
        envelope = build_event_envelope(
            event=event_name,
            source_service="payment-orchestrator",
            payload=payload
        )
        
        outbox = OutboxEvent(
            event_name=event_name,
            payload=asdict(envelope),
            status="pending"
        )
        self.db.add(outbox)
