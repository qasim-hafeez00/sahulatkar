import logging
from dataclasses import asdict
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import VirtualCard
from src.models.outbox import OutboxEvent
from sk_shared.events import EVENT_VCN_CHARGED, build_event_envelope

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
            # BV-05 Fix: Do not mutate charged_amount here, emit event to Ledger
            card.is_used = True
            logger.info(f"VCN {card.id} transaction created", extra={"order_id": card.order_id})
            
            await self._queue_event(
                EVENT_VCN_CHARGED,
                {
                    "vcn_id": card.id,
                    "order_id": card.order_id,
                    "stripe_amount_cents": data.get("amount", 0),
                    "stripe_txn_id": data.get("id"),
                }
            )

        elif event_type == "issuing_authorization.request":
            import asyncio
            import stripe
            from src.adapters.stripe_issuing import StripeIssuingAdapter
            from src.config import settings

            amount = data.get("pending_request", {}).get("amount", 0)

            stripe_adapter = StripeIssuingAdapter(
                secret_key=settings.STRIPE_SECRET_KEY,
                fx_pkr_to_usd=settings.FX_PKR_TO_USD_RATE,
                fx_buffer_pct=settings.FX_BUFFER_PCT,
            )
            # Stripe sends authorization request amounts in card currency smallest unit (USD cents).
            authorized_cents = stripe_adapter._pkr_to_usd_cents(Decimal(str(card.authorized_amount)))
            approved = card.status == "active" and amount <= authorized_cents

            if approved:
                await asyncio.to_thread(stripe.issuing.Authorization.approve, data["id"])
                logger.info("VCN authorization approved", extra={"vcn_id": card.id, "amount_cents": amount})
            else:
                await asyncio.to_thread(stripe.issuing.Authorization.decline, data["id"])
                logger.warning("VCN authorization declined", extra={"vcn_id": card.id, "amount_cents": amount, "authorized_limit": authorized_cents})
                try:
                    from src.core.metrics import VCN_AUTH_REJECTED_TOTAL
                    VCN_AUTH_REJECTED_TOTAL.inc()
                except ImportError:
                    pass

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
            payload=asdict(envelope),
            status="pending"
        )
        self.db.add(outbox)
