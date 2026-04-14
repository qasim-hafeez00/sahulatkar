from fastapi import APIRouter

from src.api.v1.admin_tracking import router as admin_tracking_router
from src.api.v1.tracking import router as tracking_router
from src.api.v1.webhooks import router as webhook_router


api_router = APIRouter()
api_router.include_router(tracking_router, prefix="/v1")
api_router.include_router(webhook_router, prefix="/v1")
api_router.include_router(admin_tracking_router, prefix="/v1")
