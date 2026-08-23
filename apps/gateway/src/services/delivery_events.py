import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.contracts import WakalahAgreement
from sk_shared.models.product import Product

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

    # Live-tested race: notification-service's own webhook handler
    # (tracking_service.py's process_aftership_webhook) publishes this same
    # event and THEN, in the same request, writes order.status = DELIVERED
    # itself — a second, independent path to the same transition. Whichever
    # commits first "wins"; the old code used order.status already matching
    # as its sole guard, so when notification-service's direct write raced
    # ahead of this listener, wakalah execution and installment rescheduling
    # below were silently skipped entirely — order ended up DELIVERED with
    # WakalahAgreement.is_executed still false and installments never
    # rescheduled off the real delivery date. Only skip the *status
    # transition/history row* when redundant; the side effects below get
    # their own idempotency checks instead, so they still run either way.
    already_delivered = order.status == target_state
    if not already_delivered:
        from_status = order.status
        order.status = target_state
        session.add(OrderStatusHistory(
            order_id=order.id,
            from_status=from_status,
            to_status=target_state,
            reason="Delivery confirmed via event",
        ))

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

    # GW-BL-15: Trigger installment activation on DELIVERED status.
    #
    # Cart orders share one Loan for unified financing (see
    # ContractSignerService.sign_murabaha): Loan.order_id only ever points at
    # the *primary* (lowest-id) sibling, while every sibling order — primary
    # included — records the shared loan via Order.loan_id. Looking the loan
    # up by `Loan.order_id == order_id` alone would silently miss this event
    # entirely for a delivery.confirmed on any non-primary sibling, so it's
    # resolved via the order's own loan_id first, falling back to the
    # single-order case where Order.loan_id may not have been set.
    from sk_shared.models.payment import Loan, Installment
    from datetime import timedelta
    loan = None
    if order.loan_id is not None:
        loan = await session.scalar(
            select(Loan).where(Loan.id == order.loan_id, Loan.status == "active")
        )
    if loan is None:
        loan = await session.scalar(
            select(Loan).where(Loan.order_id == order_id, Loan.status == "active")
        )
    if loan:
        # Update due dates to start from today + 30 days
        result = await session.execute(
            select(Installment)
            .where(Installment.loan_id == loan.id)
            .order_by(Installment.installment_number)
        )
        installments = result.scalars().all()
        
        for inst in installments:
            if inst.status == "pending":
                # Reschedule based on delivery date
                inst.due_date = (datetime.now(timezone.utc) + timedelta(days=30 * inst.installment_number)).date()

    await session.commit()
    if already_delivered:
        logger.info(f"Order {order_id} already delivered — applied wakalah/installment side effects only")
    else:
        logger.info(f"Order {order_id} transitioned from {from_status} to {target_state}")
    return True


async def apply_product_extracted_envelope(session: AsyncSession, envelope: dict) -> bool:
    """
    Product-service's scraping_worker.py publishes "product.extracted" over
    Redis pub/sub on successful extraction — nothing in this codebase ever
    subscribed to it. That left every order stuck at "url_received"/
    "processing" forever regardless of whether extraction actually
    succeeded, since Order.product_id was never set. This mirrors the
    business logic already written (but unreachable) in
    api/v1/internal.py's product_extracted_callback — credit reservation,
    down-payment calc, status transition — adapted for the pub/sub envelope
    shape and for looking the Product up by UUID (what the event payload
    actually carries; product_extracted_callback's request schema expects
    an integer id, which nothing ever sends it either).
    """
    payload = envelope.get("payload", {})
    order_id = payload.get("order_id")
    product_uuid = payload.get("product_id")
    if not order_id or not product_uuid:
        return False

    order = await session.scalar(select(Order).where(Order.id == order_id, Order.deleted_at.is_(None)))
    if not order:
        return False
    if order.status not in {OrderState.URL_RECEIVED, "url_received", "processing"}:
        return False

    product = await session.scalar(select(Product).where(Product.uuid == product_uuid))
    if not product:
        logger.error("Product %s not found while processing order %s", product_uuid, order_id)
        return False

    old_status = order.status
    down_payment_pct = 25.0
    sale_price = float(product.sale_price or 0)

    order.product_id = product.id
    order.total_amount = sale_price
    order.down_payment_amount = round(sale_price * down_payment_pct / 100.0, 2)
    order.status = OrderState.OFFER_PRESENTED

    from sk_shared.models.auth import User as UserModel
    from sk_shared.models.credit import CreditLimitHistory

    user = await session.scalar(
        select(UserModel).where(UserModel.id == order.user_id, UserModel.deleted_at.is_(None)).with_for_update()
    )
    if user and user.available_credit is not None:
        prev_available = float(user.available_credit)
        if prev_available < sale_price:
            order.status = "extraction_failed"
            session.add(OrderStatusHistory(
                order_id=order.id, from_status=old_status, to_status="extraction_failed",
                reason="INSUFFICIENT_CREDIT",
            ))
            await session.commit()
            logger.warning("Order %s extraction_failed: insufficient credit", order_id)
            return True

        user.available_credit = round(prev_available - sale_price, 2)
        history_kwargs = {"user_id": user.id}
        for attr in ["previous_limit", "old_limit", "new_limit"]:
            if hasattr(CreditLimitHistory, attr):
                history_kwargs[attr] = float(user.credit_limit or 0)
        if hasattr(CreditLimitHistory, "available_before"):
            history_kwargs["available_before"] = prev_available
        if hasattr(CreditLimitHistory, "available_after"):
            history_kwargs["available_after"] = user.available_credit
        if hasattr(CreditLimitHistory, "reason"):
            history_kwargs["reason"] = f"order_extraction_reserved:{order_id}"
        if hasattr(CreditLimitHistory, "reason_code"):
            history_kwargs["reason_code"] = "order_extraction_reserved"
        if hasattr(CreditLimitHistory, "changed_by"):
            history_kwargs["changed_by"] = "system"
        if hasattr(CreditLimitHistory, "changed_by_type"):
            history_kwargs["changed_by_type"] = "system"
        if hasattr(CreditLimitHistory, "changed_by_id"):
            history_kwargs["changed_by_id"] = "product_service"
        session.add(CreditLimitHistory(**history_kwargs))

    session.add(OrderStatusHistory(
        order_id=order.id, from_status=old_status, to_status=OrderState.OFFER_PRESENTED,
        reason="product_extraction_complete",
    ))
    await session.commit()
    logger.info(f"Order {order_id} transitioned from {old_status} to {order.status} (product_id={product.id})")
    return True


async def apply_product_extraction_failed_envelope(session: AsyncSession, envelope: dict) -> bool:
    """Mirrors api/v1/internal.py's extraction_failed_callback — same
    unreachable-endpoint gap as apply_product_extracted_envelope above."""
    payload = envelope.get("payload", {})
    order_id = payload.get("order_id")
    if not order_id:
        return False

    order = await session.scalar(select(Order).where(Order.id == order_id, Order.deleted_at.is_(None)))
    if not order:
        return False
    if order.status == "extraction_failed":
        return False

    old_status = order.status
    order.status = "extraction_failed"
    session.add(OrderStatusHistory(
        order_id=order.id, from_status=old_status, to_status="extraction_failed",
        reason=payload.get("error_message") or payload.get("error_code") or "extraction_failed",
    ))
    await session.commit()
    logger.info(f"Order {order_id} extraction_failed: {payload.get('error_code')}")
    return True
