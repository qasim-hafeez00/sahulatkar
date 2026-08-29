from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.order import Order
from src.core.logging import logger
from src.services.order_service import OrderService


async def sweep_stuck_orders(db: AsyncSession) -> list[int]:
    """HIGH-4 fix: proactively recover orders stuck in an intermediate state,
    instead of relying on a user happening to poll GET /orders/{id}/offer.

    Today the only concretely-broken "stuck" transition in this codebase is
    an order left at 'url_received' because the product-extract kickoff (or
    product-service's worker consuming it) never completed —
    OrderService.get_offer already self-heals that reactively (see
    OrderService.is_stuck_in_extraction / _mark_extraction_failed). This
    reuses that exact same logic proactively: any 'url_received' order past
    the timeout is marked 'extraction_failed' on a timer, regardless of
    whether the customer's app is even open to poll for it.

    Returns the list of order ids recovered by this sweep run, for callers
    (and tests) to assert on.
    """
    now = datetime.now(timezone.utc)
    candidates = (
        await db.execute(
            select(Order).where(Order.status == "url_received", Order.deleted_at.is_(None))
        )
    ).scalars().all()

    service = OrderService(db)
    recovered: list[int] = []
    for order in candidates:
        if not service.is_stuck_in_extraction(order, now=now):
            continue
        service._mark_extraction_failed(order, reason="proactive_stuck_order_sweep")
        recovered.append(order.id)
        logger.error(
            "ORDER_STUCK_SWEEP_RECOVERED order_id=%s from_status=url_received to_status=extraction_failed",
            order.id,
            extra={"order_id": order.id, "from_status": "url_received", "to_status": "extraction_failed"},
        )

    if recovered:
        await db.commit()

    return recovered
