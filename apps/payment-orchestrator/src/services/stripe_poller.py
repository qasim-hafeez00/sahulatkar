"""
Stripe Poller Service.

Proactively polls Stripe Issuing API for card status updates.
Used as a fallback when webhooks are delayed or lost.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sk_shared.models.payment import VirtualCard
from src.adapters.stripe_issuing import StripeIssuingAdapter
from src.config import settings

logger = logging.getLogger(__name__)

class StripePoller:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.stripe = StripeIssuingAdapter(
            secret_key=settings.STRIPE_SECRET_KEY,
            fx_pkr_to_usd=settings.FX_PKR_TO_USD_RATE,
            fx_buffer_pct=settings.FX_BUFFER_PCT,
        )

    async def poll_active_vcns(self):
        """Poll Stripe for status of all 'active' VCNs."""
        result = await self.db.execute(
            select(VirtualCard).where(VirtualCard.status == "active")
        )
        cards = result.scalars().all()
        
        for card in cards:
            try:
                # In production, we'd check for actual spend or cancellation
                stripe_card = self.stripe.get_card(card.issuer_card_id)
                if stripe_card.status == "canceled" and card.status != "expired":
                    card.status = "expired"
                    logger.info(f"Poller detected card {card.id} canceled on Stripe")
            except Exception as e:
                logger.error(f"Error polling card {card.id}: {e}")
        
        await self.db.commit()
