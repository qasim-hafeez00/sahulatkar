import contextlib
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI

from src.api.routes import api_router
from src.config import settings
from src.core.event_listeners import run_ledger_event_listener
from sk_shared.redis_client import get_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = get_redis_client(settings.redis_url, db=settings.redis_db)
    app.state.ledger_event_task = asyncio.create_task(run_ledger_event_listener(app))
    try:
        yield
    finally:
        app.state.ledger_event_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.ledger_event_task
        await app.state.redis.close()


app = FastAPI(title=f"{settings.service_name} API", version="0.1.0", lifespan=lifespan)

app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": settings.service_name}
