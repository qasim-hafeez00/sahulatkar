import asyncio
import logging
import signal
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.notification import (
    DispatchChannel, Notification, NotificationDispatch,
    NotificationStatus, DispatchStatus
)
from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client

from src.config import settings
from src.services.notification_service import NotificationService

logger = logging.getLogger("notification_consumer")

_shutdown = False

async def run_consumer() -> None:
    """Main worker loop. Processes up to CONCURRENCY jobs in parallel."""
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    semaphore = asyncio.Semaphore(settings.NOTIFICATION_WORKER_CONCURRENCY)

    logger.info("Notification consumer started", extra={"concurrency": settings.NOTIFICATION_WORKER_CONCURRENCY})

    def handle_shutdown(sig, frame):
        global _shutdown
        logger.info("Shutdown signal received", extra={"signal": sig})
        _shutdown = True

    try:
        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)
    except NotImplementedError:
        # Some environments (Windows) might not support SIGTERM/SIGINT this way
        pass

    while not _shutdown:
        try:
            # Pop notification ID from queue
            result = await redis.brpop(settings.NOTIFICATION_QUEUE_KEY, timeout=2)
            if result is None:
                continue

            notification_id = int(result[1])

            async def _process(nid: int):
                async with semaphore:
                    try:
                        async with SessionLocal() as db:
                            ns = NotificationService(db=db, redis=redis)
                            await ns.dispatch_notification(nid)
                    except Exception as e:
                        logger.error("Unhandled error in dispatch_notification", extra={"notification_id": nid, "error": str(e)})

            asyncio.create_task(_process(notification_id))
        except Exception as e:
            logger.error(f"Error in consumer loop: {e}")
            await asyncio.sleep(1)

    logger.info("Notification consumer graceful shutdown complete")

if __name__ == "__main__":
    asyncio.run(run_consumer())
