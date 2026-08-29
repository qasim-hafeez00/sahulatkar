from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import RedisNS, RedisTTL
from sk_shared.models.auth import AdminUser, User
from sk_shared.redis_client import RedisClient
from src.core.audit import record_audit_event
from src.core.dependencies import get_current_admin, get_current_user, get_db, get_redis
from src.core.rate_limit import credit_admin_rate_limit, credit_decision_rate_limit
from src.schemas.credit import (
    BlacklistRequest,
    BlacklistResponse,
    CreditApplyRequest,
    CreditApplyResponse,
    CreditCheckResponse,
    CreditEvaluateRequest,
    CreditExplanationResponse,
    CreditHistoryResponse,
    CreditOverrideRequest,
    CreditOverrideResponse,
    CreditScoreResponse,
    PrequalifyRequest,
    PrequalifyResponse,
    RecalculateResponse,
    RiskAlertsResponse,
    CreditStatusResponse,
)
from src.services.pipeline import CreditPipelineService

router = APIRouter()

def _require_self(req_user_id: str, current_user: User) -> None:
    if req_user_id != str(current_user.uuid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")


# ── CE-HIGH-01: portfolio-concentration TOCTOU guard ──────────────────────────────
# LimitEngine.check_portfolio_concentration (run inside evaluate_credit) reads the
# user's current approved exposure, and create_credit_application (below) persists a
# new approved CreditApplication row afterwards. With no lock spanning the two, two
# concurrent /credit/apply calls for the same user can both read the same
# pre-application exposure, both pass the concentration check, and both get approved
# — jointly exceeding the platform's max exposure for that user even though each
# request individually looked fine. This short-lived Redis lock (keyed on user_id,
# claimed atomically via SETNX) mirrors the installment-collection guard in
# payment-orchestrator's apps/payment-orchestrator/src/api/v1/payments.py
# (_installment_lock_key / _INSTALLMENT_LOCK_TTL_SECONDS): a second request for the
# same user arriving while the first is still mid-flight fails fast with 409 instead
# of racing it. LimitEngine.check_portfolio_concentration also takes a
# SELECT ... FOR UPDATE on the user's row as a second, DB-level layer of the same
# guard (a no-op on SQLite, real on Postgres) for any future caller that reaches it
# without going through this route.
_PORTFOLIO_LOCK_TTL_SECONDS = 30


def _portfolio_lock_key(user_id: str) -> str:
    return f"sk:credit:lock:portfolio:{user_id}"


@router.get("/credit/check", response_model=CreditCheckResponse)
async def check_credit(
    request: Request,
    order_amount: float = Query(...),
    product_category: str = Query("general"),
    is_first_order: bool = Query(False),
    device_fingerprint_hash: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
    _rate_limit: None = Depends(credit_decision_rate_limit),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    result = await pipeline.evaluate_credit(
        user_id=str(current_user.uuid),
        order_amount=order_amount,
        product_category=product_category,
        is_first_order=is_first_order,
        device_fingerprint_hash=device_fingerprint_hash,
        ip_address=request.client.host if request.client else None,
    )
    result.pop("_feature_snapshot", None)
    return result


@router.post("/credit/evaluate", response_model=CreditCheckResponse)
async def evaluate_credit(
    req: CreditEvaluateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
    _rate_limit: None = Depends(credit_decision_rate_limit),
):
    """The canonical decision core — the same evaluate_credit() call /credit/check and
    /credit/apply already run under the hood, exposed directly for internal/service-to-service
    callers that want the decision without either the query-string shape of GET /credit/check
    or /apply's side effect of creating a CreditApplication row."""
    _require_self(req.user_id, current_user)
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    result = await pipeline.evaluate_credit(
        user_id=req.user_id,
        order_amount=req.order_amount,
        product_category=req.product_category,
        is_first_order=req.is_first_order,
        device_fingerprint_hash=req.device_fingerprint_hash,
        ip_address=request.client.host if request.client else None,
    )
    result.pop("_feature_snapshot", None)
    return result


@router.post("/credit/apply", response_model=CreditApplyResponse)
async def apply_credit(
    req: CreditApplyRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _rate_limit: None = Depends(credit_decision_rate_limit),
):
    _require_self(req.user_id, current_user)

    # Scoped by user_id, not just the raw header value — two different callers reusing the
    # same Idempotency-Key string (e.g. a client-side template/counter) must never see each
    # other's cached decision. The lock is a separate, short-TTL key claimed atomically via
    # SETNX: a get-then-set pair (the previous implementation) only protects against
    # sequential retries, since two concurrent requests can both observe "not cached yet" and
    # both proceed to create a CreditApplication — the lock closes that race.
    cache_key = f"{RedisNS.CREDIT_IDEMPOTENCY}:{req.user_id}:{idempotency_key}" if idempotency_key else None
    if cache_key:
        cached = await redis_client.get_json(cache_key)
        if cached is not None:
            return cached
        claimed = await redis_client.set_nx(f"{cache_key}:lock", "1", ttl=30)
        if not claimed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A request with this Idempotency-Key is already being processed",
            )

    # CE-HIGH-01: serialize concurrent applications for this user across the
    # check-then-write window (evaluate_credit's portfolio-concentration check through
    # create_credit_application's commit) — see _portfolio_lock_key above.
    portfolio_lock_key = _portfolio_lock_key(req.user_id)
    if not await redis_client.set_nx(portfolio_lock_key, "1", ttl=_PORTFOLIO_LOCK_TTL_SECONDS):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An application for this user is already being processed",
        )

    try:
        pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
        decision = await pipeline.evaluate_credit(
            user_id=req.user_id,
            order_amount=req.order_amount,
            product_category=req.product_category,
            is_first_order=req.is_first_order,
            device_fingerprint_hash=req.device_fingerprint_hash,
            ip_address=request.client.host if request.client else None,
        )
        application = await pipeline.create_credit_application(
            user_id=req.user_id,
            requested_limit=req.requested_limit,
            application_type=req.application_type,
            decision=decision,
            background_tasks=background_tasks,
        )
    finally:
        await redis_client.delete(portfolio_lock_key)

    response = {
        "application_id": str(application.uuid),
        "status": application.status,
        "approved_limit": float(application.approved_limit) if application.approved_limit is not None else None,
        "risk_band": decision.get("risk_band"),
        "rejection_reason": application.rejection_reason,
        "manual_review_required": decision.get("manual_review_required", False),
        "outcome": decision.get("outcome"),
        "suggested_down_payment_pct": decision.get("suggested_down_payment_pct"),
    }

    if cache_key:
        await redis_client.set_json(cache_key, response, ttl=RedisTTL.CREDIT_IDEMPOTENCY)

    return response


@router.post("/credit/prequalify", response_model=PrequalifyResponse)
async def prequalify_credit(
    req: PrequalifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
    _rate_limit: None = Depends(credit_decision_rate_limit),
):
    _require_self(req.user_id, current_user)
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.prequalify(user_id=req.user_id, product_category=req.product_category)


@router.get("/credit/score", response_model=CreditScoreResponse)
async def get_credit_score(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.get_live_score(str(current_user.uuid))


@router.get("/credit/history", response_model=CreditHistoryResponse)
async def get_credit_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.get_credit_history(str(current_user.uuid), limit=limit)


@router.post("/credit/recalculate", response_model=RecalculateResponse)
async def recalculate_credit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
    _rate_limit: None = Depends(credit_decision_rate_limit),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.recalculate_limit(str(current_user.uuid))


@router.get("/credit/status", response_model=CreditStatusResponse)
async def credit_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.get_credit_status(str(current_user.uuid))


@router.get("/credit/me", response_model=CreditStatusResponse)
async def get_my_credit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.get_credit_status(str(current_user.uuid))


async def _override_and_audit(
    req: CreditOverrideRequest, request: Request, admin: AdminUser, db: AsyncSession, redis_client: RedisClient,
) -> dict:
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    result = await pipeline.admin_override_limit(
        user_id=req.user_id,
        new_limit=req.new_limit,
        reason_code=req.reason_code,
        admin_id=req.admin_id,
    )
    await record_audit_event(
        db, request,
        admin_user_id=admin.id,
        customer_user_id=result.get("customer_user_id"),
        module="credit_admin",
        action="override_limit",
        target_id=result.get("customer_user_id"),
        changes={
            "user_id": req.user_id,
            "old_limit": result.get("old_limit"),
            "new_limit": req.new_limit,
            "reason_code": req.reason_code,
            "status": result.get("status"),
        },
        severity="warning",
    )
    await db.commit()
    return result


@router.post("/admin/credit/override", response_model=CreditOverrideResponse)
async def override_credit(
    req: CreditOverrideRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
    _rate_limit: None = Depends(credit_admin_rate_limit),
):
    return await _override_and_audit(req, request, admin, db, redis_client)


@router.post("/admin/credit/adjust", response_model=CreditOverrideResponse)
async def adjust_credit(
    req: CreditOverrideRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
    _rate_limit: None = Depends(credit_admin_rate_limit),
):
    # Compatibility alias for older clients still using /adjust.
    return await _override_and_audit(req, request, admin, db, redis_client)

@router.get("/admin/risk/alerts", response_model=RiskAlertsResponse)
async def get_risk_alerts(
    limit: int = Query(20, ge=1, le=200),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    return await pipeline.get_risk_alerts(limit=limit)


@router.post("/admin/risk/blacklist", response_model=BlacklistResponse)
async def blacklist_entity(
    req: BlacklistRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
    _rate_limit: None = Depends(credit_admin_rate_limit),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    result = await pipeline.blacklist_entity(
        entity_type=req.entity_type,
        entity_value=req.entity_value,
        reason_code=req.reason_code,
        severity=req.severity,
        blacklisted_by=req.blacklisted_by,
    )
    await record_audit_event(
        db, request,
        admin_user_id=admin.id,
        module="credit_admin",
        action="blacklist_entity",
        target_id=result.get("id"),
        changes={
            "entity_type": req.entity_type, "entity_value": req.entity_value,
            "reason_code": req.reason_code, "severity": req.severity,
        },
        severity="warning",
    )
    await db.commit()
    return result


@router.get("/credit/explain/{assessment_id}", response_model=CreditExplanationResponse)
async def credit_explain(
    assessment_id: str,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    pipeline = CreditPipelineService(db_session=db, redis_client=redis_client)
    result = await pipeline.get_credit_explanation(assessment_id)
    await record_audit_event(
        db, request,
        admin_user_id=admin.id,
        module="credit_admin",
        action="view_explanation",
        target_id=result.get("id"),
        changes={"assessment_id": assessment_id, "found": result.get("found")},
    )
    await db.commit()
    return result
