from fastapi import APIRouter

from src.api.v1.admin import router as admin_router
from src.api.v1.payments import router as payments_router
from src.api.v1.vcn import router as vcn_router
from src.api.v1.webhooks import router as webhooks_router

api_router = APIRouter()
api_router.include_router(payments_router, prefix="/v1")
api_router.include_router(vcn_router, prefix="/v1")
api_router.include_router(webhooks_router, prefix="/v1")
api_router.include_router(admin_router, prefix="/v1")