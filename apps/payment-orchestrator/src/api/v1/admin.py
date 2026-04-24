"""
Admin endpoints for payment monitoring and operations.

All endpoints require admin JWT with appropriate roles.
Used by the Web Admin dashboard for payment visibility.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import PaymentTransaction, VirtualCard
from src.models.payment_workflow import PaymentWorkflow
from src.models.outbox import OutboxEvent
from src.state.payment_workflow import PaymentStatus

from src.core.dependencies import RequireRole, get_current_admin, get_db, get_redis
from src.core.metrics import RECONCILIATION_DISCREPANCY_TOTAL, RECONCILIATION_MATCHED_TOTAL
from src.schemas.admin import GatewayHealthSummary, PaginatedTransactions, TransactionSummary, VcnAdminSummary
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
    query = select(PaymentTransaction).where(PaymentTransaction.deleted_at.is_(None))

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
    txns = result.scalars().all()

    items = [
        TransactionSummary(
            id=t.id,
            order_id=None,     # TODO: Derive from loan.order_id if needed
            user_id=t.user_id,
            amount=Decimal(str(t.amount)),
            currency=t.currency,
            gateway=t.gateway,
            gateway_txn_id=t.gateway_txn_id,
            status=t.status,
            created_at=getattr(t, "created_at", None),
            reconciled_at=t.reconciled_at,
        )
        for t in txns
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
    Resets the status to INITIATED and increments attempt count.
    """
    workflow = await db.get(PaymentWorkflow, workflow_id)
    if not workflow:
        return {"error": "WORKFLOW_NOT_FOUND"}
    
    if workflow.status not in [PaymentStatus.FAILED, PaymentStatus.EXPIRED]:
        return {"error": "WORKFLOW_NOT_RETRYABLE", "status": workflow.status}
    
    workflow.status = PaymentStatus.INITIATED
    workflow.attempt_count += 1
    
    # Emit event via outbox to re-trigger whatever initiated it if needed,
    # or just let the user know they can try paying again.
    
    await db.commit()
    logger.info(f"Admin forced retry for workflow {workflow_id}")
    return {"status": "ok", "new_status": workflow.status, "attempts": workflow.attempt_count}


@router.post(
    "/adjustments",
    dependencies=[Depends(RequireRole(_FINANCE_ROLES))],
)
async def create_adjustment(
    order_id: int,
    amount_pkr: Decimal,
    reason: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """
    Issue a manual adjustment (credit or debit) for an order.
    Used for compensation or manual corrections.
    """
    # Create a manual PaymentTransaction
    txn = PaymentTransaction(
        order_id=order_id,
        user_id=0,  # System/Admin adjustment
        amount=amount_pkr,
        currency="PKR",
        gateway="system",
        gateway_txn_id=f"adj_{order_id}_{int(datetime.now().timestamp())}",
        status="success",
        transaction_type="adjustment",
        failure_message=reason,
        reconciled_at=datetime.now(timezone.utc),
    )
    db.add(txn)
    await db.commit()
    
    logger.info(f"Admin issued adjustment of {amount_pkr} for order {order_id}")
    return {"status": "ok", "adjustment_id": txn.id}


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
    from sk_shared.models.payment import PaymentTransaction, VirtualCard
    
    txns = await db.execute(
        select(PaymentTransaction).where(PaymentTransaction.order_id == order_id)
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
