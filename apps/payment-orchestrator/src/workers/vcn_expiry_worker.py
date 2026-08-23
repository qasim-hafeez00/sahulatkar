"""
VCN Expiry Worker.

Sweeps VirtualCard records that have passed their expires_at timestamp
and cancels them on Stripe Issuing so they cannot be used.

Per payments.md: "VCN expires after 24 hours — worker task cancels automatically."

INC-04 fix: Previously, the payment_expiry_worker.py only swept PaymentWorkflow
sessions. This new worker handles VirtualCard expiry via Stripe API calls.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from src.config import settings
from src.core.database import SessionLocal

logger = logging.getLogger(__name__)


class VcnExpiryWorker:
    def __init__(self):
        self.is_running = True

    async def run(self):
        logger.info("VcnExpiryWorker started")
        while self.is_running:
            try:
                await self.sweep_expired_vcns()
            except Exception as e:
                logger.error(f"Error in VcnExpiryWorker: {e}")
            await asyncio.sleep(settings.VCN_EXPIRY_SWEEP_INTERVAL_SECONDS)

    def _adapter_for_issuer(self, issuer: str):
        """Dispatches to the adapter that actually issued the card — a card's
        `issuer` column ("stripe" or "lithic") is set once at issuance time
        (see VcnService.issue_vcn), independent of the *current* value of
        FEATURE_LITHIC_ENABLED, so a card issued before a flag flip must
        still be voided through the issuer that actually holds it."""
        from src.adapters.factory import GatewayAdapterFactory

        return GatewayAdapterFactory.get(issuer, settings)

    async def sweep_expired_vcns(self):
        """
        Find all active VCNs past their expires_at and cancel them with
        whichever issuer (Stripe or Lithic) actually issued each card.
        """
        from sk_shared.models.payment import VirtualCard

        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(
                select(VirtualCard).where(
                    VirtualCard.status == "active",
                    VirtualCard.expires_at < now,
                    VirtualCard.deleted_at.is_(None),
                )
            )
            expired_cards = result.scalars().all()

            if not expired_cards:
                return

            logger.info(f"VcnExpiryWorker: sweeping {len(expired_cards)} expired VCNs")

            failed_to_cancel = []
            for card in expired_cards:
                try:
                    adapter = self._adapter_for_issuer(card.issuer)
                    # PO-CRIT-04: cancel_card() is synchronous.
                    # Run in thread pool to avoid blocking the asyncio event loop.
                    canceled = await asyncio.to_thread(
                        adapter.cancel_card, card.issuer_card_id
                    )
                    if canceled:
                        card.status = "expired"
                        logger.info(
                            "VCN expired and canceled with issuer",
                            extra={"vcn_id": card.id, "order_id": card.order_id, "issuer": card.issuer},
                        )
                        from src.core.metrics import VCN_VOID_TOTAL
                        VCN_VOID_TOTAL.labels(reason="expired").inc()
                    else:
                        # Cancel failed — still mark expired locally to prevent re-use,
                        # but log a critical alert so ops team can manually cancel with the issuer.
                        card.status = "expired"
                        failed_to_cancel.append(card.issuer_card_id)
                        logger.error(
                            "PO-CRIT-04: issuer cancel returned False for expired VCN \u2014 card may still be active with the issuer",
                            extra={"vcn_id": card.id, "issuer_card_id": card.issuer_card_id, "order_id": card.order_id, "issuer": card.issuer},
                        )
                except Exception as e:
                    logger.error(
                        "Failed to expire VCN",
                        extra={"vcn_id": card.id, "order_id": card.order_id, "error": str(e)},
                    )

            await db.commit()

            if failed_to_cancel:
                logger.critical(
                    "PO-CRIT-04: %d VCNs marked expired locally but issuer cancellation FAILED \u2014 manual review required",
                    len(failed_to_cancel),
                    extra={"issuer_card_ids": failed_to_cancel},
                )

    def stop(self):
        self.is_running = False
        logger.info("VcnExpiryWorker stop signal received")
