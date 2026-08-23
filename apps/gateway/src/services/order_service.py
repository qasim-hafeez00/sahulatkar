from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import QueueName
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.product import Product
from sk_shared.redis_client import RedisClient
from src.core.http_client import InternalServiceClient
from src.core.logging import logger


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

        # BL-05 FIX: Prevent users from spamming active orders (max 5 non-terminal orders)
        active_orders_count = await self.db.scalar(
            select(func.count(Order.id)).where(
                Order.user_id == user.id,
                Order.deleted_at.is_(None),
                Order.status.notin_(["delivered", "cancelled", "refunded", "extraction_failed"])
            )
        )
        if (active_orders_count or 0) >= 5:
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

            client = InternalServiceClient.get_client()
            await client.post(
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

    async def get_offer(self, user_id: int, order_id: int) -> dict:
        order = await self.db.scalar(
            select(Order).where(Order.id == order_id, Order.user_id == user_id, Order.deleted_at.is_(None))
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

        product = await self.db.scalar(select(Product).where(Product.id == order.product_id)) if order.product_id else None
        if not product:
            time_since_creation = (datetime.now(timezone.utc) - _ensure_utc(order.created_at)).total_seconds()
            if order.status == "url_received" and time_since_creation > 600:
                order.status = "extraction_failed"
                await self.db.commit()
                return {"status": "extraction_failed", "order_id": order.id, "reason": "Timeout waiting for extraction."}
            return {"status": "pending", "order_id": order.id}

        sale_price = float(product.sale_price or 0)
        cost_price = float(product.cost_price or sale_price)
        profit_amount = max(sale_price - cost_price, 0.0)
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
                "down_payment_pct": 25,
                "plans": [
                    {"installment_count": 3, "profit_rate_pct": 2.5},
                    {"installment_count": 4, "profit_rate_pct": 4.0},
                    {"installment_count": 6, "profit_rate_pct": 7.0},
                    {"installment_count": 12, "profit_rate_pct": 15.0},
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
