"""
Payment Orchestrator — FastAPI application entrypoint.
Handles VCN lifecycle, gateway integrations, and payment collection.
"""
import asyncio
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

    # Security: warn if internal token is too short or not set
    if not settings.INTERNAL_API_TOKEN or len(settings.INTERNAL_API_TOKEN) < 32:
        logger.warning(
            "INTERNAL_API_TOKEN is missing or shorter than 32 characters — "
            "internal auth is weakened. Rotate this token before production deployment."
        )

    # Redis connection
    app.state.redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    logger.info("Redis connection established", extra={"db": settings.REDIS_DB})

    # ── P0-03: Start OutboxPublisher background task ──────────────────────────
    from src.workers.outbox_publisher import OutboxPublisher
    outbox_publisher = OutboxPublisher(app.state.redis)
    app.state.outbox_publisher = outbox_publisher
    app.state.outbox_task = asyncio.create_task(outbox_publisher.run())
    logger.info("OutboxPublisher worker started")

    # ── P0-04: Start PaymentSessionExpiryWorker background task ──────────────
    from src.workers.payment_expiry_worker import PaymentSessionExpiryWorker
    expiry_worker = PaymentSessionExpiryWorker()
    app.state.expiry_worker = expiry_worker
    app.state.expiry_task = asyncio.create_task(expiry_worker.run())
    logger.info("PaymentSessionExpiryWorker started")

    # ── P2-01: Start VcnExpiryWorker background task ─────────────────────────
    from src.workers.vcn_expiry_worker import VcnExpiryWorker
    vcn_expiry_worker = VcnExpiryWorker()
    app.state.vcn_expiry_worker = vcn_expiry_worker
    app.state.vcn_expiry_task = asyncio.create_task(vcn_expiry_worker.run())
    logger.info("VcnExpiryWorker started")

    # ── GAP-05: Start StripePollerWorker background task ──────────────────────
    from src.workers.stripe_poller_worker import StripePollerWorker
    stripe_poller_worker = StripePollerWorker()
    app.state.stripe_poller_worker = stripe_poller_worker
    app.state.stripe_poller_task = asyncio.create_task(stripe_poller_worker.run())
    logger.info("StripePollerWorker started")

    # ── Start VcnIssueWorker background task ─────────────────────────────────
    from src.workers.vcn_issue_worker import VcnIssueWorker
    vcn_issue_worker = VcnIssueWorker(redis=app.state.redis, concurrency=settings.VCN_WORKER_CONCURRENCY)
    app.state.vcn_issue_worker = vcn_issue_worker
    app.state.vcn_issue_task = asyncio.create_task(vcn_issue_worker.run())
    logger.info("VcnIssueWorker started")

    yield

    # ── Shutdown — complete in-flight work then stop ──────────────────────────
    logger.info("payment-orchestrator shutting down — stopping workers")

    outbox_publisher.stop()
    expiry_worker.stop()
    vcn_expiry_worker.stop()
    stripe_poller_worker.stop()
    vcn_issue_worker.stop()

    # Cancel tasks and wait for graceful completion (5s budget)
    tasks = [
        app.state.outbox_task, 
        app.state.expiry_task, 
        app.state.vcn_expiry_task,
        app.state.stripe_poller_task,
        app.state.vcn_issue_task
    ]
    for task in tasks:
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

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
    # response = await call_next(request) # This can cause recursion/issues in some FastAPI versions if not careful
    try:
        response = await call_next(request)
    finally:
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
    """Liveness probe — unconditional OK (process is alive)."""
    return {"status": "ok", "service": "payment-orchestrator"}


@app.get("/health/ready", tags=["ops"])
async def readiness_check(request: Request):
    """
    Readiness probe — checks DB, Redis, and Stripe connectivity.
    GAP-09 fix: Returns 503 if any critical dependency is unreachable.
    """
    from fastapi import status
    from fastapi.responses import JSONResponse
    from src.core.health import get_readiness_status

    result = await get_readiness_status(request.app.state.redis)
    http_status = status.HTTP_200_OK if result["status"] == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=result, status_code=http_status)


@app.get("/metrics", tags=["ops"], include_in_schema=False)
async def metrics_endpoint():
    """Prometheus scrape endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
