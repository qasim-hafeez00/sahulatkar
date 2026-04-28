from fastapi import APIRouter
from src.api.v1.auth import router as auth_router
from src.api.v1.admin_auth import router as admin_auth_router
from src.api.v1.kyc import router as kyc_router
from src.api.v1.admin_kyc import router as admin_kyc_router
from src.api.v1.admin_hitl import router as admin_hitl_router
from src.api.v1.admin_dashboard import router as admin_dashboard_router
from src.api.v1.admin_analytics import router as admin_analytics_router
from src.api.v1.admin_users import router as admin_users_router
from src.api.v1.admin_orders import router as admin_orders_router
from src.api.v1.admin_payments import router as admin_payments_router
from src.api.v1.admin_installments import router as admin_installments_router
from src.api.v1.admin_risk import router as admin_risk_router
from src.api.v1.admin_system import router as admin_system_router
from src.api.v1.admin_compliance import router as admin_compliance_router, audit_router as admin_audit_router
from src.api.v1.contracts import router as contracts_router
from src.api.v1.payments import router as payments_router
from src.api.v1.orders import router as orders_router
from src.api.v1.credit import router as credit_router
from src.api.v1.webhooks import router as webhooks_router

from src.api.v1.internal import router as internal_router
from src.api.v1.admin_partners import router as admin_partners_router
from src.api.v1.admin_support import router as admin_support_router
from src.api.v1.admin_admins import router as admin_admins_router

api_router = APIRouter()


@api_router.get("/v1/health-check", tags=["system"])
async def v1_health_check() -> dict[str, str]:
	return {"status": "ok"}


api_router.include_router(auth_router, prefix="/v1")
api_router.include_router(admin_auth_router, prefix="/v1")
api_router.include_router(kyc_router, prefix="/v1")
api_router.include_router(admin_kyc_router, prefix="/v1")
api_router.include_router(admin_hitl_router, prefix="/v1")
api_router.include_router(admin_dashboard_router, prefix="/v1")
api_router.include_router(admin_analytics_router, prefix="/v1")
api_router.include_router(admin_users_router, prefix="/v1")
api_router.include_router(admin_orders_router, prefix="/v1")
api_router.include_router(admin_payments_router, prefix="/v1")
api_router.include_router(admin_installments_router, prefix="/v1")
api_router.include_router(admin_risk_router, prefix="/v1")
api_router.include_router(admin_system_router, prefix="/v1")
api_router.include_router(admin_compliance_router, prefix="/v1")
api_router.include_router(admin_audit_router, prefix="/v1")
api_router.include_router(contracts_router, prefix="/v1")
api_router.include_router(payments_router, prefix="/v1")
api_router.include_router(orders_router, prefix="/v1")
api_router.include_router(credit_router, prefix="/v1")
api_router.include_router(internal_router, prefix="/v1")
api_router.include_router(webhooks_router, prefix="/v1")
api_router.include_router(admin_partners_router, prefix="/v1")
api_router.include_router(admin_support_router, prefix="/v1")
api_router.include_router(admin_admins_router, prefix="/v1")
