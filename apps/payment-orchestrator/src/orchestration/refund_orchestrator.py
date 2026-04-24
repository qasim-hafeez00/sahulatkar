import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.events import build_event_envelope
from src.models.refund_workflow import RefundWorkflow, RefundStatus
from src.models.outbox import OutboxEvent

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
    ) -> RefundWorkflow:
        """
        Initiate a refund workflow.
        """
        existing = await self.db.scalar(
            select(RefundWorkflow).where(RefundWorkflow.refund_reference == refund_reference)
        )
        if existing:
            return existing

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

        await self._queue_event(
            "payment.refund_initiated",
            {
                "refund_id": refund.id,
                "order_id": refund.order_id,
                "amount_pkr": str(refund.amount_pkr),
                "reason": refund.reason,
            }
        )
        return refund

    async def settle_refund(self, refund_id: int, gateway_refund_id: str) -> None:
        refund = await self.db.get(RefundWorkflow, refund_id)
        if not refund:
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
            payload=envelope.to_dict(),
            status="pending"
        )
        self.db.add(outbox)
