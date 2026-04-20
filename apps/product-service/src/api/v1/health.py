from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from sk_shared.constants import QueueName

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _check_redis_health(redis_client) -> bool:
    try:
        await redis_client.redis.ping()
        return True
    except Exception as exc:
        logger.error("Redis health check failed: %s", exc)
        return False


@router.get("/health")
async def health_check(request: Request):
    redis_status = "ok" if await _check_redis_health(request.app.state.redis) else "degraded"
    return {
        "status": "ok" if redis_status == "ok" else "degraded",
        "service": "product-service",
        "redis": redis_status,
    }


@router.get("/health/live")
async def health_live():
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(request: Request):
    db_healthy = bool(getattr(request.app.state, "db_healthy", False))
    redis_healthy = await _check_redis_health(request.app.state.redis)
    listener_task = getattr(request.app.state, "listener_task", None)
    listener_healthy = bool(listener_task and not listener_task.done())

    checkout_queue_depth: int = 0
    scraping_queue_depth: int = 0
    checkout_dlq_depth: int = 0
    queue_healthy = True
    dlq_healthy = True

    if redis_healthy:
        try:
            checkout_queue_depth = await request.app.state.redis.redis.llen(QueueName.CHECKOUT)
            scraping_queue_depth = await request.app.state.redis.redis.llen(QueueName.SCRAPING)
            checkout_dlq_depth = await request.app.state.redis.redis.llen("sk:queue:dlq:checkout")
            queue_healthy = checkout_queue_depth < 1000
            dlq_healthy = checkout_dlq_depth < 50
        except Exception:
            pass

    ready = db_healthy and redis_healthy and listener_healthy
    payload = {
        "status": "ready" if ready else "not_ready",
        "db": "ok" if db_healthy else "down",
        "redis": "ok" if redis_healthy else "down",
        "event_listener": "ok" if listener_healthy else "down",
        "checkout_queue_depth": checkout_queue_depth,
        "scraping_queue_depth": scraping_queue_depth,
        "checkout_dlq_depth": checkout_dlq_depth,
        "queue_pressure": "ok" if queue_healthy else "high",
        "dlq_pressure": "ok" if dlq_healthy else "high",
    }
    if not ready:
        return JSONResponse(content=payload, status_code=503)
    return payload