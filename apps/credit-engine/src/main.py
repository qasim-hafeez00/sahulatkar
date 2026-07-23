import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from src.api.routes import router
from src.config import settings
from src.core import http_client
from src.core.metrics import setup_metrics
from sk_shared.middleware import LoggingMiddleware, RequestIdMiddleware
from sk_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Credit engine uses Redis DB 2 for velocity and assessment cache.
    app.state.redis = get_redis_client(settings.redis_url, db=2)
    http_client.start()

    yield

    await http_client.stop()
    if app.state.redis:
        await app.state.redis.close()

app = FastAPI(
    title=f"{settings.service_name} API",
    version="0.1.0",
    lifespan=lifespan
)

# No CORS here deliberately: credit-engine is only ever called server-to-server (Gateway,
# workers) — nothing in this fleet has a browser talk to it directly (see
# apps/web-customer/web-admin's gateway-proxy routes), so a CORS policy would be unused
# surface area, not a fix.
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIdMiddleware)

app.include_router(router)
setup_metrics(app)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Without this, an unhandled DB/Redis failure fell through to FastAPI/Starlette's default
    500 page — a different error envelope than every other service in this fleet returns
    (see apps/gateway/src/main.py's identical handler), which gateway/mobile clients relaying
    credit-engine errors weren't built to parse."""
    logger.error("Unhandled exception", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "INTERNAL_SERVER_ERROR"})


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "credit-engine"}
