from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


class Cart(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")  # open | checked_out | abandoned
    installment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    items: Mapped[list["CartItem"]] = relationship(
        "CartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_carts_user_id_status", "user_id", "status"),
    )


class CartItem(Base, TimestampMixin):
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cart_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True)

    cart: Mapped["Cart"] = relationship("Cart", back_populates="items")

    __table_args__ = (
        Index("ix_cart_items_cart_id", "cart_id"),
    )
