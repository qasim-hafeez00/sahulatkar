from fastapi import APIRouter

from src.api.v1.admin_tracking import router as admin_tracking_router
from src.api.v1.tracking import router as tracking_router
from src.api.v1.webhooks import router as webhook_router
from src.api.v1.notifications import router as notifications_router, internal_router as internal_notifications_router
from src.api.v1.admin_notifications import router as admin_notifications_router
from src.api.v1.health import router as health_router


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(tracking_router, prefix="/v1")
api_router.include_router(webhook_router, prefix="/v1")
api_router.include_router(admin_tracking_router, prefix="/v1")

# Notifications - Customer Facing
api_router.include_router(notifications_router, prefix="/v1/notifications", tags=["Notifications"])

# Notifications - Internal (Service-to-Service)
api_router.include_router(internal_notifications_router, prefix="/v1/internal/notifications", tags=["Internal Notifications"])

# Admin
api_router.include_router(admin_notifications_router, prefix="/v1/admin/notifications", tags=["Admin Notifications"])
