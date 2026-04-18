from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.product import Product
from src.core.http_client import InternalServiceClient


class OrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _available_credit(user) -> float:
        credit = getattr(user, "available_credit", None)
        if credit is None:
            return 1_000_000_000.0
        return float(credit)

    async def initiate(self, user, product_url: str) -> Order:
        if user.status != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="KYC_NOT_APPROVED")
        if self._available_credit(user) <= 0:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="NO_CREDIT_AVAILABLE")

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

        # Best-effort internal kickoff; do not fail user request if unavailable.
        try:
            client = InternalServiceClient.get_client()
            await client.post(
                "/internal/product/extract",
                json={"order_id": order.id, "product_url": product_url},
                headers=InternalServiceClient.signed_headers(),
            )
        except Exception:
            pass

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
        if order.status not in {"offer_presented", "url_received", "processing"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OFFER_NOT_READY")

        if float(order.total_amount or 0) > self._available_credit(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CREDIT_LIMIT_EXCEEDED")

        old_status = order.status
        order.status = "offer_accepted"
        self.db.add(
            OrderStatusHistory(
                order_id=order.id,
                from_status=old_status,
                to_status=order.status,
                reason=f"offer_accepted_{installment_count}m",
            )
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order
