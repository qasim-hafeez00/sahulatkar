import asyncio
import logging
import signal


from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client

from src.config import settings
from src.services.notification_service import NotificationService

logger = logging.getLogger("notification_consumer")


async def run_consumer(shutdown_event: asyncio.Event | None = None) -> None:
    """Main worker loop. Processes up to CONCURRENCY jobs in parallel.

    Intended to run as a background asyncio task inside notification-service's
    own FastAPI process (see src/main.py's lifespan, same pattern as
    run_scheduled_worker/run_reminder_worker/run_retry_worker) — this was
    previously only a `python -m` entrypoint with nothing in docker-compose or
    k8s ever invoking it, so nothing ever drained NOTIFICATION_QUEUE_KEY and no
    notification created via NotificationService.create_notification() (KYC,
    credit, delivery, billing, reminder events) ever actually got sent.

    `shutdown_event`, when provided, lets the FastAPI lifespan request a clean
    stop instead of the task being hard-cancelled mid-brpop. When run standalone
    via `if __name__ == "__main__"`, no shutdown_event is passed and SIGTERM/
    SIGINT are wired directly, since there's no host process managing signals
    for us in that mode.
    """
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    semaphore = asyncio.Semaphore(settings.NOTIFICATION_WORKER_CONCURRENCY)

    logger.info("Notification consumer started", extra={"concurrency": settings.NOTIFICATION_WORKER_CONCURRENCY})

    while shutdown_event is None or not shutdown_event.is_set():
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
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in consumer loop: {e}")
            await asyncio.sleep(1)

    logger.info("Notification consumer graceful shutdown complete")


if __name__ == "__main__":
    # Standalone mode (no host process managing signals for us): wire SIGTERM/
    # SIGINT directly to a shutdown_event. Not used when embedded in
    # notification-service's FastAPI app — see run_consumer()'s docstring.
    shutdown_event = asyncio.Event()

    def _handle_signal(sig, frame):
        logger.info("Shutdown signal received", extra={"signal": sig})
        shutdown_event.set()

    try:
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
    except NotImplementedError:
        # Some environments (Windows) might not support SIGTERM/SIGINT this way
        pass

    asyncio.run(run_consumer(shutdown_event))
