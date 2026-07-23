from contextlib import asynccontextmanager

import asyncio
import logging
from sqlalchemy import text

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from sk_shared.redis_client import get_redis_client
from sk_shared.database import SessionLocal

from src.api.routes import api_router
from src.api.v1.health import router as health_router
from src.config import settings, validate_critical_settings
from src.core.http_client import close_http_client, init_http_client
from src.middleware.logging import RequestLoggingMiddleware
from src.middleware.metrics import MetricsMiddleware
from src.workers.event_listener import EventListenerWorker

logger = logging.getLogger(__name__)


async def _check_db_health(retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        try:
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            if attempt == retries:
                logger.critical("DB health check failed after %s retries: %s", retries, exc)
                return False
            await asyncio.sleep(2 ** (attempt - 1))
    return False


async def _check_redis_health(redis_client) -> bool:
    try:
        await redis_client.redis.ping()
        return True
    except Exception as exc:
        logger.error("Redis health check failed: %s", exc)
        return False


async def _run_listener_forever(app: FastAPI) -> None:
    while True:
        try:
            listener = EventListenerWorker()
            app.state.event_listener = listener
            await listener.run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Event listener crashed and will restart: %s", exc)
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to boot outside `local` with missing/placeholder external
    # credentials (Rye, BrightData, Groq, INTERNAL_SERVICE_TOKEN, S3 buckets).
    try:
        validate_critical_settings()
    except RuntimeError as exc:
        logger.critical("STARTUP_ABORTED: %s", exc)
        raise

    app.state.redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    await init_http_client()

    app.state.db_healthy = await _check_db_health()
    app.state.redis_healthy = await _check_redis_health(app.state.redis)

    listener_task = asyncio.create_task(_run_listener_forever(app))
    app.state.listener_task = listener_task
    
    yield

    if getattr(app.state, "event_listener", None) is not None:
        app.state.event_listener.running = False
    listener_task.cancel()
    try:
        await asyncio.wait_for(listener_task, timeout=30)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    await close_http_client()
    await app.state.redis.close()


app = FastAPI(
    title="product-service API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(MetricsMiddleware)

FastAPIInstrumentor.instrument_app(app)

app.include_router(api_router, prefix="/api")
app.include_router(health_router)

@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
