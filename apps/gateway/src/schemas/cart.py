from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class CartItemAddRequest(BaseModel):
    product_url: HttpUrl


class CartItemView(BaseModel):
    cart_item_id: int
    order_id: int
    offer: dict


class CartResponse(BaseModel):
    cart_id: Optional[int] = None
    status: str = "empty"
    items: list[CartItemView] = Field(default_factory=list)


class CartCheckoutRequest(BaseModel):
    installment_count: Literal[3, 4, 6, 12] = 4


class CartCheckoutResponse(BaseModel):
    cart_id: int
    order_ids: list[int]
    installment_count: int
