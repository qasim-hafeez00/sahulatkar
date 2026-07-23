from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import User
from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_current_user, get_db, get_redis
from src.schemas.cart import (
    CartCheckoutRequest,
    CartCheckoutResponse,
    CartItemAddRequest,
    CartItemView,
    CartResponse,
)
from src.services.cart_service import CartService

router = APIRouter(prefix="/cart", tags=["cart"])


@router.post("/items", response_model=CartItemView, status_code=201)
async def add_cart_item(
    req: CartItemAddRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    item = await CartService(db).add_item(
        current_user,
        str(req.product_url),
        redis=redis,
        request_id=getattr(request.state, "request_id", None),
    )
    from src.services.order_service import OrderService

    offer = await OrderService(db).get_offer(current_user.id, item.order_id)
    return CartItemView(cart_item_id=item.id, order_id=item.order_id, offer=offer)


@router.get("", response_model=CartResponse)
async def get_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cart, items = await CartService(db).list_cart(current_user.id)
    if cart is None:
        return CartResponse()
    return CartResponse(
        cart_id=cart.id,
        status=cart.status,
        items=[CartItemView(**item) for item in items],
    )


@router.delete("/items/{cart_item_id}", status_code=204)
async def remove_cart_item(
    cart_item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await CartService(db).remove_item(current_user.id, cart_item_id)


@router.post("/checkout", response_model=CartCheckoutResponse)
async def checkout_cart(
    req: CartCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await CartService(db).checkout(current_user, req.installment_count)
    return CartCheckoutResponse(**result)
