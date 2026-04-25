import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.events import build_event_envelope
from src.models.payment_workflow import PaymentWorkflow, PaymentEvent
from src.models.outbox import OutboxEvent
from src.state.payment_workflow import PaymentStatus, validate_transition, PaymentWorkflowError
from src.config import settings

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
        request_id: Optional[str] = None,
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
            session_expires_at=datetime.now(timezone.utc) + timedelta(
                minutes=settings.PAYMENT_SESSION_TTL_MINUTES
            ),
        )
        self.db.add(workflow)
        await self.db.flush()

        await self._log_event(workflow, PaymentStatus.INITIATED, PaymentStatus.INITIATED, "initiate_payment")
        self._emit_transition_log(workflow, PaymentStatus.INITIATED, PaymentStatus.INITIATED, gateway, request_id)
        return workflow

    async def mark_pending(
        self,
        workflow_id: int,
        gateway_txn_id: str,
        request_id: Optional[str] = None,
    ) -> PaymentWorkflow:
        """
        Transition workflow to PENDING (async gateway redirect issued — waiting for webhook).
        """
        workflow = await self.db.get(PaymentWorkflow, workflow_id)
        if not workflow:
            raise PaymentWorkflowError(f"Payment workflow {workflow_id} not found")

        old_status = workflow.status
        validate_transition(old_status, PaymentStatus.PENDING)

        workflow.status = PaymentStatus.PENDING
        workflow.gateway_session_id = gateway_txn_id

        await self._log_event(workflow, old_status, PaymentStatus.PENDING, "gateway_redirect", metadata={"gateway_txn_id": gateway_txn_id})
        self._emit_transition_log(workflow, old_status, PaymentStatus.PENDING, workflow.gateway, request_id)
        return workflow

    async def confirm_payment(
        self,
        workflow_id: int,
        gateway_txn_id: str,
        gateway_response: dict,
        request_id: Optional[str] = None,
    ) -> PaymentWorkflow:
        """
        Transition workflow to CAPTURED.
        Valid from INITIATED (sync gateway) or PENDING (async gateway webhook).
        """
        workflow = await self.db.get(PaymentWorkflow, workflow_id)
        if not workflow:
            raise PaymentWorkflowError(f"Payment workflow {workflow_id} not found")

        old_status = workflow.status
        validate_transition(old_status, PaymentStatus.CAPTURED)

        workflow.status = PaymentStatus.CAPTURED
        workflow.gateway_session_id = gateway_txn_id
        workflow.confirmed_at = datetime.now(timezone.utc)
        workflow.captured_at = workflow.confirmed_at

        await self._log_event(workflow, old_status, PaymentStatus.CAPTURED, "gateway_confirmation", metadata=gateway_response)
        self._emit_transition_log(workflow, old_status, PaymentStatus.CAPTURED, workflow.gateway, request_id)

        # Emit domain event via Outbox
        await self._queue_event(
            "payment.confirmed",
            {
                "workflow_id": workflow.id,
                "order_id": workflow.order_id,
                "amount_pkr": str(workflow.amount_pkr),
                "gateway": workflow.gateway,
                "gateway_txn_id": gateway_txn_id,
                "x_request_id": request_id,
            }
        )

        return workflow

    async def mark_failed(
        self,
        workflow_id: int,
        error: str,
        request_id: Optional[str] = None,
    ) -> PaymentWorkflow:
        """
        Transition workflow to FAILED.
        """
        workflow = await self.db.get(PaymentWorkflow, workflow_id)
        if not workflow:
            raise PaymentWorkflowError(f"Payment workflow {workflow_id} not found")

        old_status = workflow.status
        validate_transition(old_status, PaymentStatus.FAILED)

        workflow.status = PaymentStatus.FAILED
        workflow.last_error = error
        workflow.attempt_count += 1

        await self._log_event(workflow, old_status, PaymentStatus.FAILED, "gateway_error", metadata={"error": error})
        self._emit_transition_log(workflow, old_status, PaymentStatus.FAILED, workflow.gateway, request_id)
        return workflow

    async def expire_session(self, workflow_id: int) -> None:
        workflow = await self.db.get(PaymentWorkflow, workflow_id)
        if not workflow:
            return

        if workflow.status not in {PaymentStatus.INITIATED, PaymentStatus.PENDING}:
            return

        old_status = workflow.status
        validate_transition(workflow.status, PaymentStatus.EXPIRED)
        workflow.status = PaymentStatus.EXPIRED

        await self._log_event(workflow, old_status, PaymentStatus.EXPIRED, "session_timeout")
        self._emit_transition_log(workflow, old_status, PaymentStatus.EXPIRED, workflow.gateway)
        await self._queue_event(
            "payment.session_expired",
            {
                "workflow_id": workflow.id,
                "order_id": workflow.order_id,
            }
        )

    # ── Private Helpers ──────────────────────────────────────────────────────

    def _emit_transition_log(
        self,
        workflow: PaymentWorkflow,
        from_status: PaymentStatus,
        to_status: PaymentStatus,
        gateway: str,
        request_id: Optional[str] = None,
    ) -> None:
        """Emit a structured log for every state transition (observability requirement)."""
        logger.info(
            "payment_workflow_state_transition",
            extra={
                "workflow_id": workflow.id,
                "order_id": workflow.order_id,
                "from_status": from_status.value if hasattr(from_status, "value") else str(from_status),
                "to_status": to_status.value,
                "gateway": gateway,
                "x_request_id": request_id,
            },
        )
        # Prometheus counter for transition tracking
        try:
            from src.core.metrics import WORKFLOW_STATE_TRANSITIONS_TOTAL
            WORKFLOW_STATE_TRANSITIONS_TOTAL.labels(
                from_status=from_status.value if hasattr(from_status, "value") else str(from_status),
                to_status=to_status.value,
                gateway=gateway,
            ).inc()
        except Exception:
            pass  # Metrics are best-effort

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
        """Write event to outbox table for transactional delivery."""
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
