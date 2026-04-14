from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.api.routes import router
from src.config import settings
from sk_shared.redis_client import get_redis_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Credit engine uses Redis DB 2 for velocity and assessment cache.
    app.state.redis = get_redis_client(settings.redis_url, db=2)

    yield
    
    if app.state.redis:
        await app.state.redis.close()

app = FastAPI(
    title=f"{settings.service_name} API",
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "credit-engine"}
