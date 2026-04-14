import asyncio
import contextlib
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import api_router
from src.config import settings
from sk_shared.database import SessionLocal
from sk_shared.events import EVENT_DELIVERY_CONFIRMED, EVENT_DELIVERY_STATUS_CHANGED, event_channel
from sk_shared.redis_client import get_redis_client
from src.services.delivery_events import apply_delivery_confirmed_envelope, apply_delivery_status_envelope


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
    app.state.redis = get_redis_client(settings.REDIS_URL)
    app.state.delivery_listener_task = asyncio.create_task(delivery_event_listener(app))
    yield
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "service": "gateway"}
