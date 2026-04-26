import logging
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_db, get_redis
from src.core.event_listeners import listener_state
from src.services.notification_service import DISPATCHERS
from src.core.middleware import (
    dispatcher_health, notification_queue_depth, 
    notification_retry_queue_depth, notification_dlq_depth
)
from src.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/live")
async def liveness():
    return {"status": "alive"}

@router.get("/ready")
async def readiness(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    health = {
        "status": "ready",
        "dependencies": {
            "postgres": "up",
            "redis": "up",
            "event_listener": "up" if listener_state["running"] else "down"
        }
    }
    
    # Check Postgres
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        health["dependencies"]["postgres"] = f"down: {str(e)}"
        health["status"] = "not_ready"
        logger.error(f"HEALTH_CHECK_FAILURE: Postgres down: {e}")
        
    # Check Redis
    try:
        await redis.ping()
    except Exception as e:
        health["dependencies"]["redis"] = f"down: {str(e)}"
        health["status"] = "not_ready"
        logger.error(f"HEALTH_CHECK_FAILURE: Redis down: {e}")
        
    # Check Listener
    if not listener_state["running"]:
        health["status"] = "not_ready"
        logger.error(f"HEALTH_CHECK_FAILURE: Listener not running: {listener_state}")

    try:
        main_q = await redis.llen(settings.NOTIFICATION_QUEUE_KEY)
        retry_q = await redis.llen(settings.NOTIFICATION_RETRY_QUEUE_KEY)
        dlq_q = await redis.llen(settings.NOTIFICATION_DLQ_KEY)
        
        health["queues"] = {
            "main": main_q,
            "retry": retry_q,
            "dlq": dlq_q,
        }
        notification_queue_depth.set(main_q)
        notification_retry_queue_depth.set(retry_q)
        notification_dlq_depth.set(dlq_q)
    except Exception as e:
        health["queues"] = "unknown"
        logger.error(f"HEALTH_CHECK_ERROR: Queues check failed: {e}")

    # Dispatcher Health
    health["dispatchers"] = {}
    for name, dispatcher in DISPATCHERS.items():
        try:
            is_up = await dispatcher.health_check()
            health["dispatchers"][name] = "up" if is_up else "down"
            dispatcher_health.labels(name).set(1 if is_up else 0)
            if not is_up and name in ("sms", "push"): # Critical dispatchers
                health["status"] = "degraded"
                logger.error(f"HEALTH_CHECK_FAILURE: Dispatcher {name} down")
        except Exception as e:
            health["dispatchers"][name] = "error"
            dispatcher_health.labels(name).set(0)
            logger.error(f"HEALTH_CHECK_FAILURE: Dispatcher {name} error: {e}")
        
    if health["status"] != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
    return health
