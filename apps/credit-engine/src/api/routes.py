from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_db, get_redis
from src.schemas.credit import (
    BlacklistRequest,
    BlacklistResponse,
    CreditApplyRequest,
    CreditApplyResponse,
    CreditExplanationResponse,
    CreditOverrideRequest,
    CreditOverrideResponse,
    RiskAlertsResponse,
    CreditStatusResponse,
)
from src.services.pipeline import CreditPipelineService

router = APIRouter()

@router.get("/credit/check")
async def check_credit(
    user_id: str = Query(...),
    order_amount: float = Query(...),
    product_category: str = Query("general"),
    is_first_order: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    result = await pipeline.evaluate_credit(
        user_id=user_id,
        order_amount=order_amount,
        product_category=product_category,
        is_first_order=is_first_order,
    )
    return result

@router.post("/credit/apply", response_model=CreditApplyResponse)
async def apply_credit(
    req: CreditApplyRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    decision = await pipeline.evaluate_credit(
        user_id=req.user_id,
        order_amount=req.order_amount,
        product_category=req.product_category,
        is_first_order=req.is_first_order,
    )
    application = await pipeline.create_credit_application(
        user_id=req.user_id,
        requested_limit=req.requested_limit,
        application_type=req.application_type,
        decision=decision,
    )
    return {
        "application_id": str(application.uuid),
        "status": application.status,
        "approved_limit": float(application.approved_limit) if application.approved_limit is not None else None,
        "risk_band": decision.get("risk_band"),
        "rejection_reason": application.rejection_reason,
    }


@router.get("/credit/status", response_model=CreditStatusResponse)
async def credit_status(
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.get_credit_status(user_id)


@router.get("/credit/me", response_model=CreditStatusResponse)
async def get_my_credit(
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.get_credit_status(user_id)


@router.post("/admin/credit/override", response_model=CreditOverrideResponse)
async def override_credit(
    req: CreditOverrideRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.admin_override_limit(
        user_id=req.user_id,
        new_limit=req.new_limit,
        reason_code=req.reason_code,
        admin_id=req.admin_id,
    )


@router.post("/admin/credit/adjust", response_model=CreditOverrideResponse)
async def adjust_credit(
    req: CreditOverrideRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    # Compatibility alias for older clients still using /adjust.
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.admin_override_limit(
        user_id=req.user_id,
        new_limit=req.new_limit,
        reason_code=req.reason_code,
        admin_id=req.admin_id,
    )

@router.get("/admin/risk/alerts", response_model=RiskAlertsResponse)
async def get_risk_alerts(
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.get_risk_alerts(limit=limit)


@router.post("/admin/risk/blacklist", response_model=BlacklistResponse)
async def blacklist_entity(
    req: BlacklistRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.blacklist_entity(
        entity_type=req.entity_type,
        entity_value=req.entity_value,
        reason_code=req.reason_code,
        severity=req.severity,
        blacklisted_by=req.blacklisted_by,
    )


@router.get("/credit/explain/{assessment_id}", response_model=CreditExplanationResponse)
async def credit_explain(
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.get_credit_explanation(assessment_id)
