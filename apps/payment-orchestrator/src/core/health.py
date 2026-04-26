"""
Health check utilities for /health/ready endpoint.

GAP-09 fix: The existing /health endpoint returns {"status": "ok"} unconditionally,
making it useless for Kubernetes readiness probes. This module implements real
dependency checks for DB, Redis, and gateway reachability.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def check_database() -> Dict[str, Any]:
    """Check that the database is reachable and can execute a simple query."""
    try:
        from src.core.database import SessionLocal
        from sqlalchemy import text
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Database health check failed", extra={"error": str(exc)})
        return {"status": "error", "detail": str(exc)}


async def check_redis(redis) -> Dict[str, Any]:
    """Check that Redis is reachable via a PING command."""
    try:
        await redis.redis.ping()
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Redis health check failed", extra={"error": str(exc)})
        return {"status": "error", "detail": str(exc)}


async def check_stripe() -> Dict[str, Any]:
    """
    Check Stripe API reachability (lightweight).
    Uses a balance check which is a minimal, read-only call.
    """
    try:
        from src.config import settings
        if not settings.STRIPE_SECRET_KEY:
            return {"status": "unconfigured"}
        import stripe
        import asyncio
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # Balance retrieve is a lightweight, read-only check
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: stripe.Balance.retrieve())
        
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("Stripe health check failed", extra={"error": str(exc)})
        return {"status": "error", "detail": str(exc)}


async def get_readiness_status(redis) -> Dict[str, Any]:
    """
    Aggregate readiness check for all critical dependencies.
    Returns overall status and per-dependency details.
    """
    db_status = await check_database()
    redis_status = await check_redis(redis)
    stripe_status = await check_stripe()

    all_ok = (
        db_status["status"] == "ok"
        and redis_status["status"] == "ok"
        and stripe_status["status"] in ("ok", "unconfigured")
    )

    return {
        "status": "ok" if all_ok else "degraded",
        "dependencies": {
            "database": db_status,
            "redis": redis_status,
            "stripe": stripe_status,
        },
    }
