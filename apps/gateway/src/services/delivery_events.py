import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.contracts import WakalahAgreement

logger = logging.getLogger(__name__)


async def apply_delivery_status_envelope(session: AsyncSession, envelope: dict) -> bool:
    payload = envelope.get("payload", {})
    order_id = payload.get("order_id")
    new_status_str = payload.get("new_status")

    if not order_id or not new_status_str:
        return False

    if new_status_str != "in_transit":
        return False

    target_state = OrderState.IN_TRANSIT

    order = await session.scalar(select(Order).where(Order.id == order_id))
    if not order:
        return False

    if order.status == target_state:
        return False

    from_status = order.status
    order.status = target_state

    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=target_state,
        reason="Delivery status update via event",
    )
    session.add(history)
    await session.commit()
    logger.info(f"Order {order_id} transitioned from {from_status} to {target_state}")
    return True


async def apply_delivery_confirmed_envelope(session: AsyncSession, envelope: dict) -> bool:
    payload = envelope.get("payload", {})
    order_id = payload.get("order_id")

    if not order_id:
        return False

    target_state = OrderState.DELIVERED

    order = await session.scalar(select(Order).where(Order.id == order_id))
    if not order:
        return False

    if order.status == target_state:
        return False

    from_status = order.status
    order.status = target_state

    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=target_state,
        reason="Delivery confirmed via event",
    )
    session.add(history)

    # Set WakalahAgreement.is_executed = True
    wakalah = await session.scalar(
        select(WakalahAgreement).where(
            WakalahAgreement.order_id == order_id,
            WakalahAgreement.deleted_at.is_(None)
        )
    )
    if wakalah and getattr(wakalah, "is_executed", False) is False:
        wakalah.is_executed = True
        wakalah.executed_at = datetime.now(timezone.utc)

    await session.commit()
    logger.info(f"Order {order_id} transitioned from {from_status} to {target_state}")
    return True
