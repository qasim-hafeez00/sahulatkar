from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState, QueueName
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.product import Product
from sk_shared.redis_client import RedisClient
from src.core.http_client import InternalServiceClient
from src.core.logging import logger
from src.services.system_parameters import get_effective_system_parameters, get_system_parameter


def _ensure_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime regardless of whether dt is naive or aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

PROHIBITED_KEYWORDS = [
    "tobacco",
    "cigarette",
    "alcohol",
    "liquor",
    "gambling",
    "casino",
    "betting",
    "lottery",
]


class OrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _available_credit(user) -> float:
        credit = getattr(user, "available_credit", None)
        if credit is None:
            return 1_000_000_000.0
        return float(credit)

    @staticmethod
    def _check_prohibited_url(url: str) -> None:
        url_lower = url.lower()
        for keyword in PROHIBITED_KEYWORDS:
            if keyword in url_lower:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"PROHIBITED_PRODUCT_CATEGORY: {keyword}",
                )

    @staticmethod
    def _check_prohibited_product(name: str | None, description: str | None = None, category: str | None = None) -> str | None:
        """MEDIUM fix: _check_prohibited_url only ever inspected the raw URL
        the customer submitted, at initiate() time, before extraction has
        run. A merchant page whose URL gives no hint of its contents (e.g. a
        generic product-id path) but whose extracted title/description
        turns out to name a prohibited category (tobacco, alcohol,
        gambling, ...) sailed straight through with no re-check at the
        point the real product info actually becomes known. This mirrors
        product-service's own ProhibitedCheckerService.check_text keyword
        match (see src/services/prohibited_checker.py there) against the
        now-known name/description/category, called from both
        apply_product_extraction_result's callers post-extraction. Returns
        the matched keyword, or None if the product is clean.
        """
        text = " ".join([name or "", description or "", category or ""]).lower()
        for keyword in PROHIBITED_KEYWORDS:
            if keyword in text:
                return keyword
        return None

    async def initiate(
        self,
        user,
        product_url: str,
        redis: RedisClient | None = None,
        request_id: str | None = None,
    ) -> Order:
        if user.status != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="KYC_NOT_APPROVED")
        if self._available_credit(user) <= 0:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="NO_CREDIT_AVAILABLE")
        self._check_prohibited_url(product_url)

        # BL-05 FIX: Prevent users from spamming active orders (admin-configurable cap,
        # GAP-F fix: previously hardcoded to 5 regardless of the admin-facing
        # max_active_orders SystemParameter).
        params = await get_effective_system_parameters(self.db, redis)
        max_active_orders = int(params.get("max_active_orders", 5))
        active_orders_count = await self.db.scalar(
            select(func.count(Order.id)).where(
                Order.user_id == user.id,
                Order.deleted_at.is_(None),
                Order.status.notin_(["delivered", "cancelled", "refunded", "extraction_failed"])
            )
        )
        if (active_orders_count or 0) >= max_active_orders:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="TOO_MANY_ACTIVE_ORDERS: Please complete/cancel your current orders first."
            )

        order = Order(
            user_id=user.id,
            status="url_received",
            total_amount=0,
            product_description=product_url,
        )
        self.db.add(order)
        await self.db.flush()
        self.db.add(
            OrderStatusHistory(
                order_id=order.id,
                from_status=None,
                to_status="url_received",
                reason="user_initiated_order",
            )
        )
        await self.db.commit()
        await self.db.refresh(order)

        if redis and hasattr(redis, "redis"):
            job = {
                "event": "product.extract_requested",
                "order_id": order.id,
                "product_url": product_url,
            }
            await redis.redis.lpush(QueueName.PRODUCT_EXTRACT, json.dumps(job))

        # Best-effort internal kickoff; do not fail user request if unavailable.
        #
        # Two real bugs fixed here (found live-testing the full order flow):
        # 1. InternalServiceClient's httpx.AsyncClient has no base_url at all
        #    (see core/http_client.py) — a relative path here always raised
        #    "Request URL is missing a protocol", silently swallowed by this
        #    try/except, so this call NEVER once succeeded. Build the full
        #    URL from settings.PRODUCT_SERVICE_BASE_URL instead, matching the
        #    pattern InternalServiceClient.send_otp already uses.
        # 2. product-service's ExtractRequest schema takes order_id (used to
        #    link the resulting Product back to this Order — see
        #    apply_product_extracted_envelope) — it was never sent.
        # 3. product-service's internal-auth dependency (core/dependencies.py
        #    get_current_user_id) reads the header "x-internal-service-token"
        #    — signed_headers()'s "X-Internal-Token" is gateway's OWN
        #    internal-endpoint convention (api/v1/internal.py), a different
        #    name product-service has never accepted. 403'd every call.
        #    orders.py's agent-status endpoint already works around this the
        #    same way for its own product-service call.
        try:
            from src.config import settings

            # HIGH-4 fix: this call used to go through a bare, no-retry
            # client.post() -- a single transient blip from product-service
            # (mid-restart, brief network hiccup) meant this "kickoff" never
            # happened and the order sat at url_received until either a user
            # polled GET /orders/{id}/offer past the timeout (self-heal to
            # extraction_failed) or the new proactive sweep caught it (see
            # src/services/order_recovery_sweep.py). Retrying with backoff
            # here fixes the problem closer to its source.
            await InternalServiceClient.request_with_retry(
                "POST",
                f"{settings.PRODUCT_SERVICE_BASE_URL}/api/v1/products/extract",
                json={"raw_url": product_url, "order_id": order.id, "correlation_id": request_id},
                headers={
                    "x-internal-service-token": settings.INTERNAL_SERVICE_TOKEN,
                    "X-Request-ID": request_id or "",
                    "Content-Type": "application/json",
                },
            )
        except Exception as exc:
            logger.warning("PRODUCT_EXTRACT_NUDGE_FAILED order=%s error=%s", order.id, exc)

        return order

    @staticmethod
    def is_stuck_in_extraction(order: Order, now: datetime | None = None) -> bool:
        """True when `order` has sat in 'url_received' longer than the
        extraction timeout without ever getting a product attached — i.e.
        the product-extract kickoff (or product-service's worker) never
        completed. Shared by the reactive self-heal in get_offer() (fires
        only when a user happens to poll) and the proactive sweep in
        order_recovery_sweep.py (HIGH-4 fix — fires on a timer regardless of
        whether anyone polls)."""
        if order.status != "url_received":
            return False
        now = now or datetime.now(timezone.utc)
        time_since_creation = (now - _ensure_utc(order.created_at)).total_seconds()
        from src.config import settings
        return time_since_creation > settings.ORDER_STUCK_EXTRACTION_TIMEOUT_SECONDS

    def _mark_extraction_failed(self, order: Order, reason: str) -> None:
        old_status = order.status
        order.status = "extraction_failed"
        self.db.add(
            OrderStatusHistory(
                order_id=order.id,
                from_status=old_status,
                to_status="extraction_failed",
                reason=reason,
            )
        )

    async def get_offer(self, user_id: int, order_id: int, redis: RedisClient | None = None) -> dict:
        order = await self.db.scalar(
            select(Order).where(Order.id == order_id, Order.user_id == user_id, Order.deleted_at.is_(None))
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

        product = await self.db.scalar(select(Product).where(Product.id == order.product_id)) if order.product_id else None
        if not product:
            if self.is_stuck_in_extraction(order):
                self._mark_extraction_failed(order, reason="get_offer_timeout_poll")
                await self.db.commit()
                return {"status": "extraction_failed", "order_id": order.id, "reason": "Timeout waiting for extraction."}
            return {"status": "pending", "order_id": order.id}

        sale_price = float(product.sale_price or 0)
        cost_price = float(product.cost_price or sale_price)
        profit_amount = max(sale_price - cost_price, 0.0)

        # GAP-F fix: these were hardcoded regardless of the admin System Parameters
        # panel (down_payment_pct, profit_rate_3m/4m/6m/12m) -- keep in sync with
        # ContractGeneratorService.generate_murabaha, which reads the same keys so
        # the offer shown here matches what the Murabaha contract actually charges.
        params = await get_effective_system_parameters(self.db, redis)
        return {
            "status": "ready",
            "order_id": order.id,
            "product": {
                "id": product.id,
                "name": product.name,
                "url": product.url,
                "price": sale_price,
                "brand": product.brand,
                "image_url": product.primary_image_s3,
                "availability": product.stock_status,
                "in_stock": product.in_stock,
                "variants": product.variants or [],
            },
            "financing": {
                "cost_price": cost_price,
                "profit_amount": profit_amount,
                "down_payment_pct": params.get("down_payment_pct", 25),
                "plans": [
                    {"installment_count": 3, "profit_rate_pct": params.get("profit_rate_3m", 2.5)},
                    {"installment_count": 4, "profit_rate_pct": params.get("profit_rate_4m", 4.0)},
                    {"installment_count": 6, "profit_rate_pct": params.get("profit_rate_6m", 7.0)},
                    {"installment_count": 12, "profit_rate_pct": params.get("profit_rate_12m", 15.0)},
                ],
            },
        }

    async def accept_offer(self, user, order_id: int, installment_count: int) -> Order:
        order = await self.db.scalar(
            select(Order).where(Order.id == order_id, Order.user_id == user.id, Order.deleted_at.is_(None))
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
        if order.status != "offer_presented":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OFFER_NOT_READY")

        if float(order.total_amount or 0) > self._available_credit(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CREDIT_LIMIT_EXCEEDED")

        # BL-02/TC-09: Make transition atomic so concurrent accepts cannot both succeed.
        values = {
            "status": "offer_accepted",
            "installment_count": installment_count,
        }

        transition_result = await self.db.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.user_id == user.id,
                Order.deleted_at.is_(None),
                Order.status == "offer_presented",
            )
            .values(**values)
            .returning(Order.id)
        )

        updated_order_id = transition_result.scalar_one_or_none()
        if updated_order_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OFFER_ALREADY_ACCEPTED")

        order = await self.db.scalar(
            select(Order).where(Order.id == order_id, Order.user_id == user.id, Order.deleted_at.is_(None))
        )
        
        # Credit is already reserved at extraction (internal callback)
        # We only need to record the status change history here.
        
        self.db.add(
            OrderStatusHistory(
                order_id=order.id,
                from_status="offer_presented",
                to_status="offer_accepted",
                reason=f"offer_accepted_{installment_count}m",
            )
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order


async def apply_product_extraction_result(
    db: AsyncSession,
    order: Order,
    product: Product,
    *,
    down_payment_pct: float | None = None,
) -> str:
    """MEDIUM fix (duplicated "product extracted" business logic): this is
    the single shared core of "extraction succeeded, attach the product to
    the order" logic, previously implemented almost verbatim in two
    independent places -- api/v1/internal.py's product_extracted_callback
    (the HTTP path product-service calls) and delivery_events.py's
    apply_product_extracted_envelope (the Redis pub/sub path, for when the
    callback never lands). Both computed down_payment_amount, set
    order.product_id/total_amount/status, and reserved credit; individually
    idempotent today but a real drift risk over time -- one now calls the
    other.

    Also where the MEDIUM "prohibited-category re-check" fix lives:
    OrderService._check_prohibited_url only ever inspected the raw URL at
    order-initiation time, before extraction. This re-checks the now-known
    product name/description/category and blocks+escalates to HITL on a
    match, exactly like product-service's own ProhibitedCheckerService does
    post-extraction on its side.

    Caller has already resolved `order`/`product` and is responsible for
    committing/raising/logging around the returned outcome:
      - "already_processed": order.status was already past the
        pre-extraction states; nothing was changed.
      - "prohibited": the extracted product matched a prohibited keyword;
        order marked extraction_failed and a HITL entry was created.
      - "insufficient_credit": user lacks available credit to cover the
        sale price; order marked extraction_failed.
      - "ok": order now has product_id/total_amount/down_payment_amount set
        and status advanced to OFFER_PRESENTED, credit reserved.
    Commits internally in every branch (each branch's DB writes must be
    durable regardless of which caller invoked this).
    """
    if order.status not in {OrderState.URL_RECEIVED, "url_received", "processing"}:
        return "already_processed"

    old_status = order.status

    matched_keyword = OrderService._check_prohibited_product(
        product.name, getattr(product, "description", None), getattr(product, "shariah_category", None)
    )
    if matched_keyword:
        order.status = "extraction_failed"
        db.add(OrderStatusHistory(
            order_id=order.id,
            from_status=old_status,
            to_status="extraction_failed",
            reason=f"PROHIBITED_CATEGORY_POST_EXTRACTION:{matched_keyword}",
        ))
        db.add(HitlQueue(
            order_id=order.id,
            status="pending",
            priority=2,
            failure_reason=f"PROHIBITED_CATEGORY_POST_EXTRACTION: {matched_keyword}",
        ))
        await db.commit()
        logger.warning(
            "ORDER_PROHIBITED_POST_EXTRACTION order=%s product=%s keyword=%s",
            order.id, product.id, matched_keyword,
        )
        return "prohibited"

    if down_payment_pct is None:
        down_payment_pct = float(await get_system_parameter(db, "down_payment_pct"))
    sale_price = float(product.sale_price or 0)

    order.product_id = product.id
    order.total_amount = sale_price
    order.down_payment_amount = round(sale_price * down_payment_pct / 100.0, 2)
    order.status = OrderState.OFFER_PRESENTED

    from sk_shared.models.auth import User as UserModel
    from sk_shared.models.credit import CreditLimitHistory
    from src.config import settings

    user = await db.scalar(
        select(UserModel).where(UserModel.id == order.user_id, UserModel.deleted_at.is_(None)).with_for_update()
    )
    if user and user.available_credit is not None:
        prev_available = float(user.available_credit)
        if prev_available < sale_price:
            order.status = "extraction_failed"
            db.add(OrderStatusHistory(
                order_id=order.id, from_status=old_status, to_status="extraction_failed",
                reason="INSUFFICIENT_CREDIT",
            ))
            await db.commit()
            return "insufficient_credit"

        user.available_credit = round(prev_available - sale_price, 2)

        if settings.ENVIRONMENT != "test":
            history_kwargs = {"user_id": user.id}
            for attr in ["previous_limit", "old_limit", "new_limit"]:
                if hasattr(CreditLimitHistory, attr):
                    history_kwargs[attr] = float(user.credit_limit or 0)
            if hasattr(CreditLimitHistory, "available_before"):
                history_kwargs["available_before"] = prev_available
            if hasattr(CreditLimitHistory, "available_after"):
                history_kwargs["available_after"] = user.available_credit
            if hasattr(CreditLimitHistory, "reason"):
                history_kwargs["reason"] = f"order_extraction_reserved:{order.id}"
            if hasattr(CreditLimitHistory, "reason_code"):
                history_kwargs["reason_code"] = "order_extraction_reserved"
            if hasattr(CreditLimitHistory, "changed_by"):
                history_kwargs["changed_by"] = "system"
            if hasattr(CreditLimitHistory, "changed_by_type"):
                history_kwargs["changed_by_type"] = "system"
            if hasattr(CreditLimitHistory, "changed_by_id"):
                history_kwargs["changed_by_id"] = "product_service"
            db.add(CreditLimitHistory(**history_kwargs))

    db.add(OrderStatusHistory(
        order_id=order.id, from_status=old_status, to_status=OrderState.OFFER_PRESENTED,
        reason="product_extraction_complete",
    ))
    await db.commit()
    logger.info("Order %s transitioned from %s to %s (product_id=%s)", order.id, old_status, order.status, product.id)
    return "ok"
