"""
Stripe Poller Worker.

Periodically triggers the StripePoller to check status of active VCNs.
"""
import asyncio
import logging
from src.config import settings
from src.core.database import SessionLocal
from src.services.stripe_poller import StripePoller

logger = logging.getLogger(__name__)

class StripePollerWorker:
    def __init__(self):
        self.is_running = True

    async def run(self):
        logger.info("StripePollerWorker started")
        while self.is_running:
            try:
                async with SessionLocal() as db:
                    poller = StripePoller(db)
                    await poller.poll_active_vcns()
            except Exception as e:
                logger.error(f"Error in StripePollerWorker: {e}")
            
            await asyncio.sleep(settings.VCN_STATUS_POLL_INTERVAL_SECONDS)

    def stop(self):
        self.is_running = False
        logger.info("StripePollerWorker stop signal received")
