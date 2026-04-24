"""
Payment Orchestrator — FastAPI application entrypoint.
Handles VCN lifecycle, gateway integrations, and payment collection.
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from sk_shared.redis_client import get_redis_client

from src.api.routes import api_router
from src.config import settings
from src.core.logging import setup_logging
from src.core.metrics import REQUEST_LATENCY

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    setup_logging(settings.SERVICE_NAME, settings.LOG_LEVEL)
    logger.info("payment-orchestrator starting", extra={"env": settings.ENVIRONMENT})

    app.state.redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    logger.info("Redis connection established", extra={"db": settings.REDIS_DB})

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await app.state.redis.close()
    logger.info("payment-orchestrator shutdown complete")


app = FastAPI(
    title="payment-orchestrator",
    version="0.1.0",
    description="SahulatKar Payment Orchestrator — VCN Lifecycle, Gateway Integrations, Reconciliation",
    lifespan=lifespan,
    docs_url="/docs" if True else None,  # disable in production via env flag
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next) -> Response:
    """Record per-endpoint request latency for Prometheus."""
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)
    return response


@app.middleware("http")
async def request_id_middleware(request: Request, call_next) -> Response:
    """Propagate or generate X-Request-ID for distributed tracing."""
    import uuid
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(api_router, prefix="/api")


@app.get("/health", tags=["ops"])
async def health_check():
    return {"status": "ok", "service": "payment-orchestrator"}


@app.get("/metrics", tags=["ops"], include_in_schema=False)
async def metrics_endpoint():
    """Prometheus scrape endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
