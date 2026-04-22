import contextlib
from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from src.api.routes import api_router
from src.config import settings
from src.events.listener import run_ledger_event_listener
from src.core.logging import configure_logging
from src.core.middleware import RequestIDMiddleware
from sk_shared.redis_client import get_redis_client


logger = logging.getLogger(__name__)

configure_logging()


def _start_listener_task(app: FastAPI) -> asyncio.Task:
    task = asyncio.create_task(run_ledger_event_listener(app))
    logger.info("Started ledger event listener task")
    return task


async def _watch_listener(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(2)
        task = app.state.ledger_event_task
        if task.done():
            with contextlib.suppress(asyncio.CancelledError):
                exc = task.exception()
                if exc is not None:
                    logger.exception("Ledger event listener crashed; restarting", exc_info=exc)
            app.state.ledger_event_task = _start_listener_task(app)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = get_redis_client(settings.redis_url, db=settings.redis_db)
    app.state.ledger_event_task = _start_listener_task(app)
    app.state.ledger_event_watchdog_task = asyncio.create_task(_watch_listener(app))
    try:
        yield
    finally:
        app.state.ledger_event_watchdog_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.ledger_event_watchdog_task

        app.state.ledger_event_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.ledger_event_task
        await app.state.redis.close()


app = FastAPI(title=f"{settings.service_name} API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)

# Prometheus metrics endpoint
@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Optional OpenTelemetry Integration
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    
    trace.set_tracer_provider(TracerProvider())
    FastAPIInstrumentor.instrument_app(app)
    # SQLAlchemy instrumentation requires the engine, which is created in database.py
    # We leave that for a more advanced DI setup, but FastAPI is now instrumented.
    logger.info("OpenTelemetry instrumentation enabled.")
except ImportError:
    logger.info("OpenTelemetry not installed; skipping instrumentation.")

app.include_router(api_router)


@app.get("/health")
async def health_check():
    listener_task = getattr(app.state, "ledger_event_task", None)
    watchdog_task = getattr(app.state, "ledger_event_watchdog_task", None)
    return {
        "status": "ok",
        "service": settings.service_name,
        "listener_running": bool(listener_task and not listener_task.done()),
        "watchdog_running": bool(watchdog_task and not watchdog_task.done()),
    }


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
