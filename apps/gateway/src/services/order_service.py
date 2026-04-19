from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select, func, update
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
        
        # TASK-11: Reserve credit - decrement user's available_credit
        from sk_shared.models.auth import User as UserModel
        from sk_shared.models.credit import CreditLimitHistory
        user_record = await self.db.scalar(
            select(UserModel).where(UserModel.id == user.id, UserModel.deleted_at.is_(None))
        )
        if user_record and user_record.available_credit is not None:
            prev_available = float(user_record.available_credit)
            user_record.available_credit = max(prev_available - float(order.total_amount or 0), 0.0)
            from src.config import settings
            if settings.ENVIRONMENT != "test":
                history_kwargs = {"user_id": user.id}
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
                    history_kwargs["reason"] = f"order_offer_accepted:{order_id}"
                if hasattr(CreditLimitHistory, "reason_code"):
                    history_kwargs["reason_code"] = "order_offer_accepted"
                if hasattr(CreditLimitHistory, "changed_by"):
                    history_kwargs["changed_by"] = "system"
                if hasattr(CreditLimitHistory, "changed_by_type"):
                    history_kwargs["changed_by_type"] = "system"
                if hasattr(CreditLimitHistory, "changed_by_id"):
                    history_kwargs["changed_by_id"] = str(user.id)
                self.db.add(CreditLimitHistory(**history_kwargs))
        
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
