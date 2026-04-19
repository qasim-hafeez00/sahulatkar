from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import User
from sk_shared.models.delivery import Shipment, TrackingEvent
from sk_shared.models.order import Order, OrderStatusHistory
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
    return OrderInitiateResponse(order_id=order.id, status="processing") # GAP-05


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
        installment_count=order.installment_count,
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
            installment_count=row.installment_count,
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
        installment_count=order.installment_count,
        created_at=order.created_at,
        product_id=order.product_id,
        product_description=order.product_description,
    )


@router.get("/{order_id}/tracking")
async def get_order_tracking(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id, Order.deleted_at.is_(None))
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    shipment = await db.scalar(
        select(Shipment).where(Shipment.order_id == order_id, Shipment.deleted_at.is_(None))
    )
    if shipment is None:
        return {
            "order_id": order_id,
            "order_status": order.status,
            "shipment": None,
            "message": "Shipment not yet dispatched",
        }

    latest_event = await db.scalar(
        select(TrackingEvent)
        .where(TrackingEvent.shipment_id == shipment.id)
        .order_by(TrackingEvent.event_time.desc())
    )

    return {
        "order_id": order_id,
        "order_status": order.status,
        "shipment": {
            "tracking_number": shipment.tracking_number,
            "courier": shipment.courier_name,
            "status": shipment.status,
            "estimated_delivery": shipment.estimated_delivery.isoformat() if shipment.estimated_delivery else None,
            "last_event": (
                {
                    "event_code": latest_event.event_code,
                    "event_description": latest_event.event_description,
                    "location_city": latest_event.location_city,
                    "event_time": latest_event.event_time.isoformat(),
                }
                if latest_event
                else None
            ),
        },
    }


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """TASK-12: Cancel an order and restore reserved credit if applicable"""
    from datetime import datetime, timezone
    from sk_shared.constants import OrderState
    from sk_shared.models.auth import User as UserModel
    from sk_shared.models.credit import CreditLimitHistory
    
    # Only these states allow cancellation
    CANCELLABLE_STATES = {"url_received", "offer_presented", "offer_accepted", "extraction_failed"}
    
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.id,
            Order.deleted_at.is_(None),
        )
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
    
    if order.status not in CANCELLABLE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"ORDER_NOT_CANCELLABLE (current status: {order.status})",
        )

    old_status = order.status
    order.status = "cancelled"
    order.deleted_at = datetime.now(timezone.utc)  # Soft delete

    # Restore reserved credit if offer was accepted
    if old_status == "offer_accepted":
        from src.config import settings

        user_record = await db.scalar(
            select(UserModel).where(UserModel.id == current_user.id, UserModel.deleted_at.is_(None))
        )
        if user_record and user_record.available_credit is not None:
            prev_available = float(user_record.available_credit)
            user_record.available_credit = prev_available + float(order.total_amount or 0)
            if settings.ENVIRONMENT != "test":
                history_kwargs = {"user_id": current_user.id}
                if hasattr(CreditLimitHistory, "previous_limit"):
                    history_kwargs["previous_limit"] = float(user_record.credit_limit or 0)
                if hasattr(CreditLimitHistory, "old_limit"):
                    history_kwargs["old_limit"] = float(user_record.credit_limit or 0)
                if hasattr(CreditLimitHistory, "new_limit"):
                    history_kwargs["new_limit"] = float(user_record.credit_limit or 0)
                if hasattr(CreditLimitHistory, "available_before"):
                    history_kwargs["available_before"] = prev_available
                if hasattr(CreditLimitHistory, "available_after"):
                    history_kwargs["available_after"] = user_record.available_credit
                if hasattr(CreditLimitHistory, "reason"):
                    history_kwargs["reason"] = f"order_cancelled_credit_restored:{order_id}"
                if hasattr(CreditLimitHistory, "reason_code"):
                    history_kwargs["reason_code"] = "order_cancelled_credit_restored"
                if hasattr(CreditLimitHistory, "changed_by"):
                    history_kwargs["changed_by"] = "system"
                if hasattr(CreditLimitHistory, "changed_by_type"):
                    history_kwargs["changed_by_type"] = "system"
                if hasattr(CreditLimitHistory, "changed_by_id"):
                    history_kwargs["changed_by_id"] = str(current_user.id)
                db.add(CreditLimitHistory(**history_kwargs))

    db.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=old_status,
            to_status="cancelled",
            reason="user_cancelled",
        )
    )
    await db.commit()
    return {"order_id": order_id, "status": "cancelled"}
