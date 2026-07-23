"""
Admin endpoints for payment monitoring and operations.

All endpoints require admin JWT with appropriate roles.
Used by the Web Admin dashboard for payment visibility.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import Loan, PaymentTransaction, VirtualCard
from src.models.payment_workflow import PaymentWorkflow
from src.models.outbox import OutboxEvent
from src.state.payment_workflow import PaymentStatus

from src.core.dependencies import RequireRole, get_current_admin, get_db, get_redis
from src.core.metrics import RECONCILIATION_DISCREPANCY_TOTAL, RECONCILIATION_MATCHED_TOTAL
from src.schemas.admin import AdjustmentRequest, GatewayHealthSummary, PaginatedTransactions, TransactionSummary, VcnAdminSummary
from src.schemas.reconciliation import ReconciliationImportRequest, ReconciliationReport
from src.services.reconciliation import ReconciliationService
from src.services.routing_engine import GatewayRoutingEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/payments", tags=["admin-payments"])

_FINANCE_ROLES = ["superadmin", "finance"]
_READ_ROLES = ["superadmin", "finance", "support"]


@router.get(
    "/transactions",
    response_model=PaginatedTransactions,
    dependencies=[Depends(RequireRole(_READ_ROLES))],
)
async def list_transactions(
    db: AsyncSession = Depends(get_db),
    gateway: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _admin=Depends(get_current_admin),
):
    """List all payment transactions with filtering by gateway and status."""
    # PaymentTransaction already has an order_id FK column (see
    # packages/shared-python/sk_shared/models/payment.py), but every
    # transaction-creation call site in src/api/v1/payments.py only sets
    # loan_id/installment_id, leaving order_id NULL — so it could never be
    # read straight off the row (this is what the "order_id=None # TODO"
    # below used to do). No Alembic migration is needed since the column
    # already exists; the fix is to derive it via Loan instead. Left-join
    # Loan so every transaction can still be traced back to its originating
    # order for the admin dashboard: t.order_id wins if a row happens to
    # have it set directly (e.g. a future direct-to-order transaction type),
    # otherwise fall back to loan.order_id.
    query = (
        select(PaymentTransaction, Loan.order_id.label("loan_order_id"))
        .outerjoin(Loan, PaymentTransaction.loan_id == Loan.id)
        .where(PaymentTransaction.deleted_at.is_(None))
    )

    if gateway:
        query = query.where(PaymentTransaction.gateway == gateway)
    if status:
        query = query.where(PaymentTransaction.status == status)

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.scalar(count_q)) or 0

    # Paginate
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(PaymentTransaction.id.desc()).offset(offset).limit(page_size)
    )
    rows = result.all()

    items = [
        TransactionSummary(
            id=t.id,
            order_id=t.order_id if t.order_id is not None else loan_order_id,
            user_id=t.user_id,
            amount=Decimal(str(t.amount)),
            currency=t.currency,
            gateway=t.gateway,
            gateway_txn_id=t.gateway_txn_id,
            status=t.status,
            created_at=getattr(t, "created_at", None),
            reconciled_at=t.reconciled_at,
        )
        for t, loan_order_id in rows
    ]

    return PaginatedTransactions(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/vcns",
    response_model=list[VcnAdminSummary],
    dependencies=[Depends(RequireRole(_READ_ROLES))],
)
async def list_vcns(
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _admin=Depends(get_current_admin),
):
    """List VCNs with optional status filter."""
    query = select(VirtualCard).where(VirtualCard.deleted_at.is_(None))
    if status:
        query = query.where(VirtualCard.status == status)

    result = await db.execute(query.order_by(VirtualCard.id.desc()).limit(limit))
    cards = result.scalars().all()

    return [
        VcnAdminSummary(
            vcn_id=c.id,
            order_id=c.order_id,
            user_id=c.user_id,
            status=c.status,
            masked_number=c.masked_number,
            authorized_amount=float(c.authorized_amount),
            charged_amount=float(c.charged_amount),
            issued_at=c.issued_at,
            expires_at=c.expires_at,
            void_reason=getattr(c, "void_reason", None),
        )
        for c in cards
    ]


@router.get(
    "/gateway-health",
    response_model=list[GatewayHealthSummary],
    dependencies=[Depends(RequireRole(_READ_ROLES))],
)
async def gateway_health(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """Get current health status of all payment gateways."""
    redis = request.app.state.redis
    engine = GatewayRoutingEngine(redis)
    summaries = await engine.get_health_summary()
    return [GatewayHealthSummary(**s) for s in summaries]


@router.post(
    "/reconciliation",
    response_model=ReconciliationReport,
    dependencies=[Depends(RequireRole(_FINANCE_ROLES))],
)
async def run_reconciliation(
    payload: ReconciliationImportRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """
    Run payment-level reconciliation for a gateway settlement batch.
    Upload gateway settlement records; returns discrepancy report.
    """
    service = ReconciliationService(db)
    report = await service.reconcile(payload)

    RECONCILIATION_MATCHED_TOTAL.labels(gateway=payload.gateway).inc(report.matched)
    RECONCILIATION_DISCREPANCY_TOTAL.labels(
        gateway=payload.gateway, type="total"
    ).inc(report.discrepancies)

    return report
@router.get(
    "/workflows",
    dependencies=[Depends(RequireRole(_READ_ROLES))],
)
async def list_workflows(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _admin=Depends(get_current_admin),
):
    """List all payment workflows."""
    query = select(PaymentWorkflow).order_by(PaymentWorkflow.id.desc())
    
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    workflows = result.scalars().all()
    
    return workflows


@router.post(
    "/workflows/{workflow_id}/force-retry",
    dependencies=[Depends(RequireRole(_FINANCE_ROLES))],
)
async def force_retry_workflow(
    workflow_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """
    Force a retry of a failed payment workflow.
    Resets the status to INITIATED and invalidates the old idempotency key.

    INR-06 fix: The idempotency key is suffixed with _retry_{count} so a fresh
    payment attempt by the user doesn't immediately short-circuit back to this
    (now-reset) workflow via the key collision path.
    """
    workflow = await db.get(PaymentWorkflow, workflow_id)
    if not workflow:
        return {"error": "WORKFLOW_NOT_FOUND"}

    if workflow.status not in [PaymentStatus.FAILED, PaymentStatus.EXPIRED]:
        return {"error": "WORKFLOW_NOT_RETRYABLE", "status": workflow.status}

    old_attempt = workflow.attempt_count
    workflow.status = PaymentStatus.INITIATED
    workflow.attempt_count = old_attempt + 1
    workflow.last_error = None

    # INR-06: Invalidate the stale idempotency key so the next payment attempt
    # creates a fresh workflow instead of returning this one.
    workflow.idempotency_key = f"{workflow.idempotency_key}_retry_{workflow.attempt_count}"

    await db.commit()
    logger.info(
        "Admin forced retry for workflow",
        extra={"workflow_id": workflow_id, "attempt_count": workflow.attempt_count},
    )
    return {
        "status": "ok",
        "new_status": workflow.status,
        "attempts": workflow.attempt_count,
        "new_idempotency_key": workflow.idempotency_key,
    }


@router.post(
    "/adjustments",
    dependencies=[Depends(RequireRole(_FINANCE_ROLES))],
)
async def create_adjustment(
    body: AdjustmentRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """
    Issue a manual adjustment (credit or debit) for an order.
    Used for compensation or manual corrections.
    """
    # BV-05 fix: Derive loan_id from order_id. PaymentTransaction links to Loan,
    # not directly to Order.
    from sk_shared.models.payment import Loan
    loan = await db.scalar(select(Loan).where(Loan.order_id == body.order_id))
    if not loan:
        raise HTTPException(status_code=404, detail="LOAN_NOT_FOUND_FOR_ORDER")

    # Emit outbox event instead of creating PaymentTransaction directly
    from sk_shared.events import build_event_envelope
    from src.models.outbox import OutboxEvent
    from dataclasses import asdict

    envelope = build_event_envelope(
        event="payment.adjustment_requested",
        source_service="payment-orchestrator",
        payload={
            "order_id": body.order_id,
            "loan_id": loan.id,
            "amount_pkr": str(body.amount_pkr),
            "reason": body.reason,
        }
    )
    outbox = OutboxEvent(
        event_name="payment.adjustment_requested",
        payload=asdict(envelope),
        status="pending"
    )
    db.add(outbox)
    await db.commit()

    logger.info(f"Admin queued adjustment of {body.amount_pkr} for order {body.order_id}")
    return {"status": "queued", "event": "payment.adjustment_requested"}


@router.get(
    "/audit-trail/{order_id}",
    dependencies=[Depends(RequireRole(_READ_ROLES))],
)
async def get_audit_trail(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """
    Download a consolidated audit trail for an order's payments.
    """
    from sk_shared.models.payment import PaymentTransaction, VirtualCard, Loan
    
    txns = await db.execute(
        select(PaymentTransaction)
        .join(Loan, PaymentTransaction.loan_id == Loan.id)
        .where(Loan.order_id == order_id)
    )
    cards = await db.execute(
        select(VirtualCard).where(VirtualCard.order_id == order_id)
    )
    
    trail = {
        "order_id": order_id,
        "transactions": [
            {
                "id": t.id,
                "amount": str(t.amount),
                "gateway": t.gateway,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in txns.scalars().all()
        ],
        "vcns": [
            {
                "id": c.id,
                "status": c.status,
                "charged_amount": str(c.charged_amount),
                "issued_at": c.issued_at.isoformat() if c.issued_at else None,
            }
            for c in cards.scalars().all()
        ]
    }
    
    return trail


# ── PO-EP-04: Admin-triggerable reconciliation ──────────────────────────────
@router.post(
    "/reconciliation/trigger",
    dependencies=[Depends(RequireRole(_FINANCE_ROLES))],
)
async def trigger_reconciliation(
    gateway: str,
    settlement_date: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """
    PO-EP-04: Manually trigger settlement reconciliation for a specific gateway
    and date without needing to run the CLI worker.
    """
    from datetime import date as _date
    from src.workers.reconciliation_worker import run_reconciliation
    import asyncio

    try:
        parsed_date = _date.fromisoformat(settlement_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="INVALID_DATE_FORMAT: use YYYY-MM-DD")

    if gateway not in ["jazzcash", "safepay", "raast", "stripe", "easypaisa"]:
        raise HTTPException(status_code=400, detail="UNSUPPORTED_GATEWAY")

    # Run async reconciliation as a background task
    asyncio.create_task(run_reconciliation(gateway, parsed_date))
    logger.info("Admin triggered reconciliation", extra={"gateway": gateway, "date": settlement_date})
    return {"status": "triggered", "gateway": gateway, "settlement_date": settlement_date}


# ── PO-EP-05: Admin view of user's Raast mandates ───────────────────────
@router.get(
    "/mandates/{user_id}",
    dependencies=[Depends(RequireRole(_READ_ROLES))],
)
async def get_user_mandates(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """
    PO-EP-05: View all active payment mandates for a specific user.
    Used to verify Raast auto-debit setup for installment collection.
    PO-BL-07: Implements full mandate management (replaces empty STUB).
    """
    from src.models.payment_mandate import PaymentMandate

    result = await db.execute(
        select(PaymentMandate).where(PaymentMandate.user_id == user_id)
        .order_by(PaymentMandate.id.desc())
    )
    mandates = result.scalars().all()

    return {
        "user_id": user_id,
        "mandates": [
            {
                "id": m.id,
                "gateway": m.gateway,
                "mandate_reference": m.mandate_reference,
                "status": m.status,
                "payer_identifier": m.payer_identifier,
                "max_amount_per_txn": str(m.max_amount_per_txn) if m.max_amount_per_txn else None,
                "expires_at": m.expires_at.isoformat() if m.expires_at else None,
                "last_used_at": m.last_used_at.isoformat() if m.last_used_at else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mandates
        ],
    }
