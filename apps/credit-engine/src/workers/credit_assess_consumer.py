import asyncio
import json
import logging

from sk_shared.constants import QueueName, RedisNS
from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client
from src.config import settings
from src.services.pipeline import CreditPipelineService

logger = logging.getLogger(__name__)


async def process_job(redis_client, payload: dict) -> None:
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Credit assess job missing user_id")
        return

    order_amount = float(payload.get("order_amount") or 1000.0)

    async with SessionLocal() as db:
        service = CreditPipelineService(db_session=db, redis_client=redis_client)
        decision = await service.evaluate_credit(
            user_id=user_id,
            order_amount=order_amount,
            product_category=payload.get("product_category", "general"),
            is_first_order=bool(payload.get("is_first_order", True)),
        )

        await service.create_credit_application(
            user_id=user_id,
            requested_limit=decision.get("approved_limit") or order_amount,
            application_type="periodic_review",
            decision=decision,
        )

        cache_key = f"{RedisNS.CREDIT_USER}:{user_id}:latest"
        await redis_client.set_json(cache_key, decision, ttl=3600)
        logger.info("Processed credit assessment for user_id=%s", user_id)


async def run_consumer() -> None:
    redis_client = get_redis_client(settings.redis_url, db=2)
    logger.info("Starting credit assessment consumer on queue=%s", QueueName.CREDIT_ASSESS)

    try:
        while True:
            item = await redis_client.redis.brpop(QueueName.CREDIT_ASSESS, timeout=5)
            if not item:
                continue

            try:
                payload = json.loads(item[1])
            except (json.JSONDecodeError, TypeError):
                logger.exception("Invalid queue payload")
                continue

            try:
                await process_job(redis_client, payload)
            except Exception:
                logger.exception("Credit assessment job failed")
    finally:
        await redis_client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_consumer())
