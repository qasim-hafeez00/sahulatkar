from fastapi import APIRouter

from src.api.v1.finance import router as finance_router


api_router = APIRouter()
api_router.include_router(finance_router)