from fastapi import APIRouter

from src.api.v1.admin import router as admin_router
from src.api.v1.products import router as products_router


api_router = APIRouter()
api_router.include_router(products_router, prefix="/v1")
api_router.include_router(admin_router, prefix="/v1")
