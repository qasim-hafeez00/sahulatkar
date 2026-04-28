from __future__ import annotations

import json

from fastapi import HTTPException, status
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import QueueName
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.product import Product
from sk_shared.redis_client import RedisClient
from src.core.http_client import InternalServiceClient
from src.core.logging import logger

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
        try:
            client = InternalServiceClient.get_client()
            await client.post(
                "/v1/products/extract",
                json={"raw_url": product_url},
                headers=InternalServiceClient.signed_headers(request_id=request_id),
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
            import datetime
            time_since_creation = (datetime.datetime.now(datetime.timezone.utc) - order.created_at.replace(tzinfo=datetime.timezone.utc)).total_seconds()
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
