import json
import uuid
from datetime import datetime, timezone
import logging

from sk_shared.redis_client import RedisClient

logger = logging.getLogger(__name__)

SERVICE_NAME = "product-service"

def build_event_envelope(
    event: str,
    payload: dict,
    correlation_id: str | None = None,
) -> dict:
    return {
        "event": event,
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_service": SERVICE_NAME,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "payload": payload,
    }

async def publish_event(
    redis: RedisClient,
    event: str,
    payload: dict,
    correlation_id: str | None = None,
) -> None:
    envelope = build_event_envelope(event, payload, correlation_id)
    channel = f"sk:events:{event}"
    await redis.redis.publish(channel, json.dumps(envelope))
    logger.info("Published event %s to %s", event, channel)
