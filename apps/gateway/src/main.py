import asyncio
import contextlib
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from src.core.rate_limit import rate_limit_middleware
from src.api.routes import api_router
from src.config import settings, validate_critical_settings
from sk_shared.database import SessionLocal
from src.core.dependencies import get_db
from sk_shared.events import EVENT_DELIVERY_CONFIRMED, EVENT_DELIVERY_STATUS_CHANGED, event_channel
from sk_shared.redis_client import get_redis_client
from src.services.delivery_events import (
    apply_delivery_confirmed_envelope,
    apply_delivery_status_envelope,
    apply_product_extracted_envelope,
    apply_product_extraction_failed_envelope,
)

EVENT_PRODUCT_EXTRACTED = "product.extracted"
EVENT_PRODUCT_EXTRACTION_FAILED = "product.extraction_failed"
from src.core.http_client import InternalServiceClient
from src.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from src.core.logging import setup_logging, logger
from src.core.metrics import setup_metrics


async def delivery_event_listener(app: FastAPI) -> None:
    channels = [
        event_channel(EVENT_DELIVERY_STATUS_CHANGED),
        event_channel(EVENT_DELIVERY_CONFIRMED),
        event_channel(EVENT_PRODUCT_EXTRACTED),
        event_channel(EVENT_PRODUCT_EXTRACTION_FAILED),
    ]
    pubsub = app.state.redis.redis.pubsub()
    await pubsub.subscribe(*channels)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                await asyncio.sleep(0.01)
                continue

            data = message.get("data")
            if isinstance(data, bytes):
                raw = data.decode("utf-8")
            elif isinstance(data, str):
                raw = data
            else:
                continue

            try:
                envelope = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event_name = envelope.get("event")

            # This listener runs once per uvicorn worker process (4 here) —
            # Redis pub/sub fans a single publish out to every subscriber,
            # so with no dedup every event was processed once per worker.
            # Harmless for the delivery handlers (idempotent status checks
            # mostly caught it), but apply_product_extracted_envelope's
            # credit-reservation deduction isn't idempotent against a
            # same-process-generation race: live-tested and reproduced a
            # genuine double-deduction (two workers both read
            # status="url_received" before either committed the transition
            # to "offer_presented"). Dedup by event_id — same SETNX pattern
            # already used for the AfterShip webhook in notification-service.
            event_id = envelope.get("event_id")
            if event_id:
                claimed = await app.state.redis.redis.set(
                    f"sk:events:dedup:{event_id}", "1", nx=True, ex=300
                )
                if not claimed:
                    continue

            # BUG-08 FIX: Wrap DB session block in try/except to prevent listener death on DB errors
            try:
                async with SessionLocal() as session:
                    if event_name == EVENT_DELIVERY_STATUS_CHANGED:
                        await apply_delivery_status_envelope(session, envelope)
                    elif event_name == EVENT_DELIVERY_CONFIRMED:
                        await apply_delivery_confirmed_envelope(session, envelope)
                    elif event_name == EVENT_PRODUCT_EXTRACTED:
                        await apply_product_extracted_envelope(session, envelope)
                    elif event_name == EVENT_PRODUCT_EXTRACTION_FAILED:
                        await apply_product_extraction_failed_envelope(session, envelope)
            except Exception as exc:
                logger.error("Delivery event processing failed event=%s error=%s", event_name, exc, exc_info=True)
                # Continue the loop — do not propagate; individual message errors must not kill the listener
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(*channels)
        await pubsub.close()


async def listener_watchdog(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(10)
        task = getattr(app.state, "delivery_listener_task", None)
        if task and task.done():
            exc = task.exception() if not task.cancelled() else None
            logger.error("Delivery listener died (exc=%s), restarting...", exc)
            app.state.delivery_listener_task = asyncio.create_task(delivery_event_listener(app))


async def verify_critical_tables():
    """Verify that admin-related tables exist to prevent runtime 501s."""
    tables = ["system_parameters", "risk_blacklist"]
    async with SessionLocal() as db:
        for table in tables:
            try:
                await db.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
            except Exception:
                logger.warning("CRITICAL_TABLE_MISSING: Table '%s' not found in database. Admin modules may be degraded.", table)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Initializing Gateway Lifespan...")

    # Validate production configuration before accepting traffic
    try:
        validate_critical_settings()
    except RuntimeError as exc:
        logger.critical("STARTUP_ABORTED: %s", exc)
        raise

    app.state.redis = get_redis_client(settings.REDIS_URL)
    app.state.delivery_listener_task = asyncio.create_task(delivery_event_listener(app))
    app.state.delivery_watchdog_task = asyncio.create_task(listener_watchdog(app))

    await verify_critical_tables()

    InternalServiceClient.start()
    yield
    logger.info("Shutting down Gateway Lifespan...")
    await InternalServiceClient.stop()
    app.state.delivery_watchdog_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await app.state.delivery_watchdog_task
    app.state.delivery_listener_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await app.state.delivery_listener_task
    await app.state.redis.close()


app = FastAPI(
    title="Gateway API - SahulatKar",
    description="Main entrypoint for SahulatKar clients",
    version="1.0.0",
    lifespan=lifespan
)

def _resolve_cors_origins() -> list[str]:
    if settings.CORS_ORIGINS:
        return [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
    origins = ["https://app.sahulatkar.pk", "https://admin.sahulatkar.pk"]
    if settings.ENVIRONMENT != "production":
        origins += ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000"]
    return origins


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def apply_rate_limit(request, call_next):
    return await rate_limit_middleware(request, call_next)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "INTERNAL_SERVER_ERROR"}
    )


app.include_router(api_router, prefix="/api")
setup_metrics(app)


@app.get("/health", tags=["system"])
async def health_check(db=Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))

        listener_healthy = True
        if hasattr(app.state, "delivery_listener_task"):
            if app.state.delivery_listener_task.done():
                listener_healthy = False
                try:
                    app.state.delivery_listener_task.result()
                except Exception as e:
                    logger.error("Delivery listener task failed: %s", e)

        try:
            if hasattr(app.state, "redis") and app.state.redis is not None:
                await app.state.redis.redis.ping()
        except Exception:
            return {"status": "degraded", "service": "gateway", "redis": "unreachable"}

        if not listener_healthy:
            return {"status": "degraded", "service": "gateway", "listener": "down"}

        return {"status": "ok", "service": "gateway"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "service": "gateway", "db": "unreachable"})
