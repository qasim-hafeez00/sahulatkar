import asyncio
import contextlib
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from src.core.rate_limit import rate_limit_middleware
from src.api.routes import api_router
from src.config import settings
from sk_shared.database import SessionLocal
from sk_shared.events import EVENT_DELIVERY_CONFIRMED, EVENT_DELIVERY_STATUS_CHANGED, event_channel
from sk_shared.redis_client import get_redis_client
from src.services.delivery_events import apply_delivery_confirmed_envelope, apply_delivery_status_envelope
from src.core.http_client import InternalServiceClient
from src.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from src.core.logging import setup_logging, logger
from src.core.metrics import setup_metrics

async def delivery_event_listener(app: FastAPI) -> None:
    channels = [event_channel(EVENT_DELIVERY_STATUS_CHANGED), event_channel(EVENT_DELIVERY_CONFIRMED)]
    pubsub = app.state.redis.redis.pubsub()
    await pubsub.subscribe(*channels)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                await asyncio.sleep(0.05)
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
            async with SessionLocal() as session:
                if event_name == EVENT_DELIVERY_STATUS_CHANGED:
                    await apply_delivery_status_envelope(session, envelope)
                elif event_name == EVENT_DELIVERY_CONFIRMED:
                    await apply_delivery_confirmed_envelope(session, envelope)
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(*channels)
        await pubsub.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Initializing Gateway Lifespan...")
    app.state.redis = get_redis_client(settings.REDIS_URL)
    app.state.delivery_listener_task = asyncio.create_task(delivery_event_listener(app))
    InternalServiceClient.start()
    yield
    logger.info("Shutting down Gateway Lifespan...")
    await InternalServiceClient.stop()
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

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.sahulatkar.pk",
        "https://admin.sahulatkar.pk"
    ],
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
async def health_check():
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        await app.state.redis.redis.ping()
        return {"status": "ok", "service": "gateway"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "service": "gateway"})
