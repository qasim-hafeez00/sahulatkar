from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sk_shared.redis_client import get_redis_client

from src.api.routes import api_router
from src.config import settings
from src.services.aftership_client import AfterShipClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    app.state.aftership_client = AfterShipClient(api_key=settings.AFTERSHIP_API_KEY, base_url=settings.AFTERSHIP_BASE_URL)
    yield
    await app.state.aftership_client.aclose()
    await app.state.redis.close()


app = FastAPI(
    title="Notification & Tracking Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "notification-service"}
