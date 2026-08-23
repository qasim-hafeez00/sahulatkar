import asyncio
import logging
from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client
from src.config import settings
from src.services.retry_service import RetryService

logger = logging.getLogger("retry_worker")

async def process_retry_queue() -> None:
    """
    Poll the database for pending retries that have reached their backoff time,
    and re-enqueue them into the main dispatch queue.
    """
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    
    async with SessionLocal() as db:
        retry_service = RetryService(db=db)
        due_dispatches = await retry_service.get_due_retries(limit=100)
        
        if not due_dispatches:
            return

        # Get unique notification IDs to avoid duplicate queueing
        notification_ids = {d.notification_id for d in due_dispatches}
        
        for nid in notification_ids:
            await redis.lpush(settings.NOTIFICATION_QUEUE_KEY, str(nid))
            
        logger.info(f"Re-enqueued {len(notification_ids)} notifications for retry")

async def run_retry_worker(interval_seconds: int = 300) -> None:
    """
    Continuous loop: re-enqueue due retries every `interval_seconds`. Same gap
    as reminder_worker — process_retry_queue() previously had no scheduler
    calling it in production, so a dispatch that failed and was marked
    RETRYING with a backoff never actually got a second attempt. Intended to
    be started as a background asyncio task alongside the main FastAPI app.
    """
    logger.info("Retry worker started", extra={"interval_seconds": interval_seconds})
    while True:
        try:
            await process_retry_queue()
        except Exception as exc:
            logger.error("Retry worker sweep failed", extra={"error": str(exc)})
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(process_retry_queue())
