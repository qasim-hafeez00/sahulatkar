from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from sqlalchemy.ext.asyncio import async_sessionmaker

from sk_shared.database import engine
from sk_shared.redis_client import get_redis_client

from src.api.routes import api_router
from src.config import settings
from src.core.event_listeners import start_event_listener
from src.core.logging import setup_logging
from src.core.middleware import RequestIDMiddleware, PrometheusMiddleware
from src.services.aftership_client import AfterShipClient
from src.workers.scheduled_worker import run_scheduled_worker

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize shared state
    app.state.redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    app.state.aftership_client = AfterShipClient(
        api_key=settings.AFTERSHIP_API_KEY,
        base_url=settings.AFTERSHIP_BASE_URL,
    )
    app.state.db_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Start background event listener
    listener_task = await start_event_listener(app)
    app.state.listener_task = listener_task

    # NS-BL-09: Start scheduled notification worker (fires ScheduledNotification records)
    import asyncio
    scheduled_task = asyncio.create_task(run_scheduled_worker(interval_seconds=60))
    app.state.scheduled_task = scheduled_task

    yield

    # Graceful shutdown
    if listener_task and not listener_task.done():
        listener_task.cancel()
    if hasattr(app.state, "scheduled_task") and not app.state.scheduled_task.done():
        app.state.scheduled_task.cancel()
    await app.state.aftership_client.aclose()
    await app.state.redis.close()


app = FastAPI(
    title="SahulatKar Notification & Tracking Service",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
)

# Middleware (order matters — outermost applied last)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_allow_origins_list,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(PrometheusMiddleware)
app.add_middleware(RequestIDMiddleware)

# API routes
app.include_router(api_router, prefix="/api")

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health", include_in_schema=False)
async def health_check():
    return {"status": "ok", "service": settings.SERVICE_NAME}
