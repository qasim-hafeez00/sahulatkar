from fastapi import APIRouter

from src.api.v1.finance import router as finance_router
from src.api.v1.health import router as health_router
from src.api.v1.accounts import router as accounts_router
from src.api.v1.periods import router as periods_router
from src.api.v1.entries import router as entries_router


api_router = APIRouter()
api_router.include_router(finance_router)
api_router.include_router(health_router)
api_router.include_router(accounts_router)
api_router.include_router(periods_router)
api_router.include_router(entries_router)