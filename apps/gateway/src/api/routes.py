from fastapi import APIRouter
from src.api.v1.auth import router as auth_router
from src.api.v1.admin_auth import router as admin_auth_router
from src.api.v1.kyc import router as kyc_router
from src.api.v1.admin_kyc import router as admin_kyc_router
from src.api.v1.admin_hitl import router as admin_hitl_router
from src.api.v1.admin_dashboard import router as admin_dashboard_router
from src.api.v1.admin_users import router as admin_users_router
from src.api.v1.admin_orders import router as admin_orders_router
from src.api.v1.admin_payments import router as admin_payments_router
from src.api.v1.contracts import router as contracts_router
from src.api.v1.payments import router as payments_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/v1")
api_router.include_router(admin_auth_router, prefix="/v1")
api_router.include_router(kyc_router, prefix="/v1")
api_router.include_router(admin_kyc_router, prefix="/v1")
api_router.include_router(admin_hitl_router, prefix="/v1")
api_router.include_router(admin_dashboard_router, prefix="/v1")
api_router.include_router(admin_users_router, prefix="/v1")
api_router.include_router(admin_orders_router, prefix="/v1")
api_router.include_router(admin_payments_router, prefix="/v1")
api_router.include_router(contracts_router, prefix="/v1")
api_router.include_router(payments_router, prefix="/v1")
