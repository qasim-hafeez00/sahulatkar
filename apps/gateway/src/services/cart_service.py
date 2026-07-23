from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.models.auth import User
from sk_shared.models.cart import Cart, CartItem
from sk_shared.models.credit import CreditLimitHistory
from sk_shared.models.order import Order
from sk_shared.redis_client import RedisClient
from src.config import settings
from src.services.order_service import OrderService


class CartService:
    """Groups multiple single-product Orders into one cart for unified financing.

    Each cart item is a full Order created via the existing OrderService.initiate
    pipeline (same extraction/credit/prohibited-URL checks). "Unified financing"
    is achieved at Murabaha-signing time (see ContractSignerService.sign_murabaha),
    which consolidates all of a cart's signed contracts into one shared Loan.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_open_cart(self, user_id: int) -> Cart | None:
        return await self.db.scalar(
            select(Cart).where(Cart.user_id == user_id, Cart.status == "open")
        )

    async def _get_or_create_open_cart(self, user_id: int) -> Cart:
        cart = await self._get_open_cart(user_id)
        if cart:
            return cart
        cart = Cart(user_id=user_id, status="open")
        self.db.add(cart)
        await self.db.flush()
        return cart

    async def add_item(
        self,
        user: User,
        product_url: str,
        redis: RedisClient | None,
        request_id: str | None,
    ) -> CartItem:
        cart = await self._get_or_create_open_cart(user.id)
        order = await OrderService(self.db).initiate(
            user, product_url, redis=redis, request_id=request_id
        )
        item = CartItem(cart_id=cart.id, order_id=order.id)
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_cart(self, user_id: int) -> tuple[Cart | None, list[dict]]:
        cart = await self._get_open_cart(user_id)
        if not cart:
            return None, []

        items = (
            await self.db.execute(
                select(CartItem).where(CartItem.cart_id == cart.id).order_by(CartItem.id.asc())
            )
        ).scalars().all()

        order_service = OrderService(self.db)
        results = []
        for item in items:
            offer = await order_service.get_offer(user_id, item.order_id)
            results.append({"cart_item_id": item.id, "order_id": item.order_id, "offer": offer})
        return cart, results

    async def remove_item(self, user_id: int, cart_item_id: int) -> None:
        item = await self.db.scalar(
            select(CartItem)
            .join(Cart, Cart.id == CartItem.cart_id)
            .where(
                CartItem.id == cart_item_id,
                Cart.user_id == user_id,
                Cart.status == "open",
            )
        )
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CART_ITEM_NOT_FOUND")

        order = await self.db.scalar(select(Order).where(Order.id == item.order_id))
        if order is None:
            await self.db.delete(item)
            await self.db.commit()
            return

        # Items in an open cart have never gone through accept_offer, so the widest
        # state they can be in is OFFER_PRESENTED (credit already reserved there).
        removable_states = {OrderState.URL_RECEIVED, OrderState.OFFER_PRESENTED, OrderState.EXTRACTION_FAILED}
        if order.status not in removable_states:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CART_ITEM_NOT_REMOVABLE")

        if order.status == OrderState.OFFER_PRESENTED:
            user_record = await self.db.scalar(select(User).where(User.id == user_id))
            if user_record and user_record.available_credit is not None:
                prev_available = float(user_record.available_credit)
                user_record.available_credit = round(prev_available + float(order.total_amount or 0), 2)
                if settings.ENVIRONMENT != "test":
                    history_kwargs = {"user_id": user_id}
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
                        history_kwargs["reason"] = f"cart_item_removed_credit_restored:{cart_item_id}"
                    if hasattr(CreditLimitHistory, "reason_code"):
                        history_kwargs["reason_code"] = "cart_item_removed_credit_restored"
                    if hasattr(CreditLimitHistory, "changed_by"):
                        history_kwargs["changed_by"] = "system"
                    if hasattr(CreditLimitHistory, "changed_by_type"):
                        history_kwargs["changed_by_type"] = "system"
                    if hasattr(CreditLimitHistory, "changed_by_id"):
                        history_kwargs["changed_by_id"] = "cart_service"
                    self.db.add(CreditLimitHistory(**history_kwargs))

        order.status = OrderState.CANCELLED
        order.deleted_at = datetime.now(timezone.utc)
        await self.db.delete(item)
        await self.db.commit()

    async def checkout(self, user: User, installment_count: int) -> dict:
        cart = await self._get_open_cart(user.id)
        if not cart:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CART_EMPTY")

        items = (
            await self.db.execute(select(CartItem).where(CartItem.cart_id == cart.id))
        ).scalars().all()
        if not items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CART_EMPTY")

        order_service = OrderService(self.db)
        accepted_order_ids: list[int] = []
        for item in items:
            order = await order_service.accept_offer(user, item.order_id, installment_count)
            accepted_order_ids.append(order.id)

        cart.status = "checked_out"
        cart.installment_count = installment_count
        await self.db.commit()

        return {
            "cart_id": cart.id,
            "order_ids": accepted_order_ids,
            "installment_count": installment_count,
        }
