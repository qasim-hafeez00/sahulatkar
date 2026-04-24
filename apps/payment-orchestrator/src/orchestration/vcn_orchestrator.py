import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import VirtualCard
from src.models.outbox import OutboxEvent
from sk_shared.events import build_event_envelope

logger = logging.getLogger(__name__)


class VcnOrchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def handle_stripe_event(self, event_type: str, data: dict):
        """
        Handle Stripe Issuing events to track VCN usage.
        """
        card_id = data.get("card")
        if not card_id:
            # For some events, card ID is deeper in the object
            card_id = data.get("object", {}).get("card")
        
        if not card_id:
            logger.warning(f"Stripe event {event_type} missing card ID")
            return

        card = await self.db.scalar(
            select(VirtualCard).where(VirtualCard.issuer_card_id == card_id)
        )
        if not card:
            logger.warning(f"VCN not found for Stripe card {card_id}")
            return

        if event_type == "issuing_transaction.created":
            amount = Decimal(str(data.get("amount", 0))) / Decimal("100")  # Stripe amounts are in cents
            card.charged_amount += amount
            card.is_used = True
            logger.info(f"VCN {card.id} charged {amount} PKR", extra={"order_id": card.order_id})
            
            await self._queue_event(
                "vcn.charged",
                {
                    "vcn_id": card.id,
                    "order_id": card.order_id,
                    "amount_pkr": str(amount),
                    "total_charged": str(card.charged_amount),
                }
            )

        elif event_type == "issuing_card.updated":
            status = data.get("status")
            if status == "inactive" and card.status == "active":
                card.status = "inactive"
                logger.info(f"VCN {card.id} deactivated via Stripe")

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
