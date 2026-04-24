import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.events import build_event_envelope
from src.models.payment_workflow import PaymentWorkflow, PaymentEvent
from src.models.outbox import OutboxEvent
from src.state.payment_workflow import PaymentStatus, validate_transition, PaymentWorkflowError

logger = logging.getLogger(__name__)


class PaymentOrchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def initiate_payment(
        self,
        *,
        order_id: int,
        user_id: int,
        amount_pkr: Decimal,
        gateway: str,
        idempotency_key: str,
        session_ttl_minutes: int = 30,
    ) -> PaymentWorkflow:
        """
        Initiate a new payment workflow.
        Idempotent: returns existing workflow if idempotency_key is seen.
        """
        existing = await self.db.scalar(
            select(PaymentWorkflow).where(PaymentWorkflow.idempotency_key == idempotency_key)
        )
        if existing:
            return existing

        workflow = PaymentWorkflow(
            order_id=order_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            status=PaymentStatus.INITIATED,
            gateway=gateway,
            amount_pkr=amount_pkr,
            session_expires_at=datetime.now(timezone.utc) + timedelta(minutes=session_ttl_minutes),
        )
        self.db.add(workflow)
        await self.db.flush()

        await self._log_event(workflow, PaymentStatus.INITIATED, PaymentStatus.INITIATED, "initiate_payment")
        return workflow

    async def confirm_payment(
        self,
        workflow_id: int,
        gateway_txn_id: str,
        gateway_response: dict,
    ) -> PaymentWorkflow:
        """
        Transition workflow to AUTHORIZED or CAPTURED based on gateway response.
        """
        workflow = await self.db.get(PaymentWorkflow, workflow_id)
        if not workflow:
            raise PaymentWorkflowError(f"Payment workflow {workflow_id} not found")

        old_status = workflow.status
        # For now, we transition to CAPTURED directly as most of our gateways are sync or simple
        new_status = PaymentStatus.CAPTURED 

        validate_transition(old_status, new_status)

        workflow.status = new_status
        workflow.gateway_session_id = gateway_txn_id
        workflow.confirmed_at = datetime.now(timezone.utc)
        
        await self._log_event(workflow, old_status, new_status, "gateway_confirmation", metadata=gateway_response)
        
        # Emit domain event via Outbox
        await self._queue_event(
            "payment.confirmed",
            {
                "workflow_id": workflow.id,
                "order_id": workflow.order_id,
                "amount_pkr": str(workflow.amount_pkr),
                "gateway": workflow.gateway,
                "gateway_txn_id": gateway_txn_id,
            }
        )
        
        return workflow

    async def expire_session(self, workflow_id: int) -> None:
        workflow = await self.db.get(PaymentWorkflow, workflow_id)
        if not workflow:
            return

        if workflow.status != PaymentStatus.INITIATED:
            return

        old_status = workflow.status
        validate_transition(workflow.status, PaymentStatus.EXPIRED)
        workflow.status = PaymentStatus.EXPIRED
        
        await self._log_event(workflow, old_status, PaymentStatus.EXPIRED, "session_timeout")
        await self._queue_event(
            "payment.session_expired",
            {
                "workflow_id": workflow.id,
                "order_id": workflow.order_id,
            }
        )

    async def _log_event(
        self, 
        workflow: PaymentWorkflow, 
        from_status: PaymentStatus,
        to_status: PaymentStatus, 
        trigger: str,
        metadata: Optional[dict] = None
    ):
        event = PaymentEvent(
            payment_workflow_id=workflow.id,
            from_status=from_status.value if hasattr(from_status, "value") else str(from_status),
            to_status=to_status.value,
            trigger=trigger,
            metadata_json=metadata
        )
        self.db.add(event)

    async def _queue_event(self, event_name: str, payload: dict):
        # Build Sk envelope
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
