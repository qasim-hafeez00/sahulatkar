from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.models.order import Order, OrderStatusHistory


DELIVERY_TO_ORDER_STATE = {
    "in_transit": OrderState.IN_TRANSIT,
    "out_for_delivery": OrderState.IN_TRANSIT,
    "delivered": OrderState.DELIVERED,
}


async def apply_delivery_status_envelope(db: AsyncSession, envelope: dict[str, Any]) -> bool:
    payload = envelope.get("payload") or {}
    order_id = _safe_int(payload.get("order_id"))
    if order_id is None:
        return False

    mapped_state = DELIVERY_TO_ORDER_STATE.get(str(payload.get("new_status") or "").lower())
    if mapped_state is None:
        return False

    return await _transition_order_state(db, order_id=order_id, new_state=mapped_state, reason="delivery.status_changed")


async def apply_delivery_confirmed_envelope(db: AsyncSession, envelope: dict[str, Any]) -> bool:
    payload = envelope.get("payload") or {}
    order_id = _safe_int(payload.get("order_id"))
    if order_id is None:
        return False

    return await _transition_order_state(db, order_id=order_id, new_state=OrderState.DELIVERED, reason="delivery.confirmed")


async def _transition_order_state(db: AsyncSession, *, order_id: int, new_state: str, reason: str) -> bool:
    order = await db.scalar(select(Order).where(Order.id == order_id, Order.deleted_at.is_(None)))
    if order is None:
        return False

    if order.status == new_state:
        return False

    from_status = order.status
    order.status = new_state
    db.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=from_status,
            to_status=new_state,
            reason=reason,
        )
    )
    await db.commit()
    return True


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
