from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import User
from sk_shared.models.order import Order
from src.core.dependencies import get_current_user, get_db
from src.schemas.orders import (
    OrderAcceptRequest,
    OrderDetailResponse,
    OrderInitiateRequest,
    OrderInitiateResponse,
    OrderOfferResponse,
    OrderSummary,
)
from src.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/initiate", response_model=OrderInitiateResponse)
async def initiate_order(
    req: OrderInitiateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await OrderService(db).initiate(current_user, str(req.product_url))
    return OrderInitiateResponse(order_id=order.id, status="processing")


@router.get("/{order_id}/offer", response_model=OrderOfferResponse)
async def get_order_offer(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OrderService(db).get_offer(current_user.id, order_id)


@router.post("/{order_id}/accept", response_model=OrderDetailResponse)
async def accept_order_offer(
    order_id: int,
    req: OrderAcceptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await OrderService(db).accept_offer(current_user, order_id, req.installment_count)
    return OrderDetailResponse(
        id=order.id,
        status=order.status,
        total_amount=float(order.total_amount),
        down_payment_amount=float(order.down_payment_amount) if order.down_payment_amount is not None else None,
        created_at=order.created_at,
        product_id=order.product_id,
        product_description=order.product_description,
    )


@router.get("", response_model=list[OrderSummary])
async def list_my_orders(
    status_filter: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.user_id == current_user.id, Order.deleted_at.is_(None))
    if status_filter:
        query = query.where(Order.status == status_filter)
    rows = (await db.execute(query.order_by(Order.created_at.desc()))).scalars().all()
    return [
        OrderSummary(
            id=row.id,
            status=row.status,
            total_amount=float(row.total_amount),
            down_payment_amount=float(row.down_payment_amount) if row.down_payment_amount is not None else None,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/{order_id}", response_model=OrderDetailResponse)
async def get_my_order_detail(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id, Order.deleted_at.is_(None))
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    return OrderDetailResponse(
        id=order.id,
        status=order.status,
        total_amount=float(order.total_amount),
        down_payment_amount=float(order.down_payment_amount) if order.down_payment_amount is not None else None,
        created_at=order.created_at,
        product_id=order.product_id,
        product_description=order.product_description,
    )
