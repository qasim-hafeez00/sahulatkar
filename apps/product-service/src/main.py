from contextlib import asynccontextmanager

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from sk_shared.redis_client import get_redis_client

from src.api.routes import api_router
from src.config import settings
from src.middleware.logging import RequestLoggingMiddleware
from src.middleware.metrics import MetricsMiddleware
from src.workers.event_listener import EventListenerWorker


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    
    # Start event listener in background
    listener = EventListenerWorker()
    listener_task = asyncio.create_task(listener.run())
    app.state.event_listener = listener
    
    yield
    
    listener.running = False
    listener_task.cancel()
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


@app.get("/health")
async def health_check():
    try:
        await app.state.redis.redis.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "degraded"
        
    return {
        "status": "ok" if redis_status == "ok" else "degraded",
        "service": "product-service",
        "redis": redis_status,
    }

@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
