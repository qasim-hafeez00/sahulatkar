import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState, QueueName
from sk_shared.models.auth import User
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.payment import Installment, Loan, PaymentTransaction
from sk_shared.redis_client import RedisClient
from src.core.audit import record_audit_event
from src.core.dependencies import get_current_user, get_db, get_redis
from src.schemas.payments import (
    DownPaymentRequest,
    DownPaymentResponse,
    InstallmentDetail,
    PaymentScheduleResponse,
    VcnIssueRequest,
    VcnIssueResponse,
)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/vcn/issue", response_model=VcnIssueResponse)
async def issue_vcn(
    req: VcnIssueRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    order = await db.scalar(
        select(Order).where(
            Order.id == req.order_id,
            Order.user_id == current_user.id,
            Order.deleted_at.is_(None),
        )
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    if order.status not in (OrderState.DOWN_PAYMENT_RECEIVED,):
        if order.status == OrderState.CONTRACTS_SIGNED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="DOWN_PAYMENT_NOT_CONFIRMED",
            )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="VCN_GATE_NOT_PASSED")
        
    old_status = order.status
    order.status = "pending_vcn"
    db.add(OrderStatusHistory(
        order_id=order.id, 
        from_status=old_status,
        to_status="pending_vcn", 
        reason="vcn_issue_requested",
    ))
    # We delay committing until end of logic normally, but here audit expects to log the action.

    await record_audit_event(
        db=db,
        request=request,
        customer_user_id=current_user.id,
        module="payments",
        action="vcn_issue_requested",
        target_id=order.id,
        changes={"order_id": order.id},
    )

    vcn_job = json.dumps({
        "event": "vcn.issue_requested",
        "order_id": order.id,
        "user_id": current_user.id,
        "amount": float(order.total_amount),
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    })
    if hasattr(redis, "redis"):
        await redis.redis.lpush(QueueName.VCN_ISSUE, vcn_job)

    await db.commit()
    return VcnIssueResponse(status="queued", order_id=order.id)


@router.post("/down-payment", response_model=DownPaymentResponse)
async def create_down_payment(
    req: DownPaymentRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    order = await db.scalar(
        select(Order).where(
            Order.id == req.order_id,
            Order.user_id == current_user.id,
            Order.deleted_at.is_(None),
        )
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
    if order.status != OrderState.CONTRACTS_SIGNED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CONTRACTS_NOT_SIGNED")

    expected = float(order.down_payment_amount or 0)
    if abs(float(req.amount_pkr) - expected) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DOWN_PAYMENT_AMOUNT_MISMATCH")

    old_status = order.status
    order.status = OrderState.DOWN_PAYMENT_RECEIVED
    db.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=old_status,
            to_status=OrderState.DOWN_PAYMENT_RECEIVED,
            reason="down_payment_initiated",
        )
    )

    payment = PaymentTransaction(
        user_id=current_user.id,
        order_id=order.id,
        amount=float(req.amount_pkr),
        gateway=req.method,
        status="initiated",
    )
    db.add(payment)
    # Don't commit yet to avoid split transaction with audit trail
    
    await record_audit_event(
        db=db,
        request=request,
        customer_user_id=current_user.id,
        module="payments",
        action="down_payment_initiated",
        target_id=order.id,
        changes={
            "order_id": order.id,
            "amount_pkr": str(req.amount_pkr),
            "method": req.method,
        },
    )
    
    await db.commit()
    await db.refresh(payment)
    
    payment_job = json.dumps({
        "event": "payment.initiate_requested",
        "payment_id": payment.id,
        "order_id": order.id,
        "user_id": current_user.id,
        "amount": float(req.amount_pkr),
        "gateway": req.method,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    })
    if hasattr(redis, "redis"):
        await redis.redis.lpush(QueueName.PAYMENT_INITIATE, payment_job)

    return DownPaymentResponse(
        payment_id=payment.id,
        status=payment.status,
        transaction_id=getattr(payment, "gateway_txn_id", None),
        checkout_url=None, # Will be set by webhook or orchestrator
    )


@router.get("/schedule/{order_id}", response_model=PaymentScheduleResponse)
async def get_payment_schedule(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    loan = await db.scalar(
        select(Loan).where(
            Loan.order_id == order_id,
            Loan.user_id == current_user.id,
            Loan.deleted_at.is_(None),
        )
    )
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LOAN_NOT_FOUND")

    installments = (
        await db.execute(
            select(Installment).where(
                Installment.loan_id == loan.id,
                Installment.deleted_at.is_(None),
            ).order_by(Installment.installment_number.asc())
        )
    ).scalars().all()

    return PaymentScheduleResponse(
        loan_id=loan.id,
        loan_number=loan.loan_number,
        total_amount=loan.total_repayable,
        installments=[
            InstallmentDetail(
                number=i.installment_number,
                due_date=i.due_date,
                amount=i.total_amount,
                status=i.status,
                paid_at=i.paid_at,
            )
            for i in installments
        ],
    )
