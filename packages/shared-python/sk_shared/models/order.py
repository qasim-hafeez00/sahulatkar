from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin, SoftDeleteMixin


class Order(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=True) # GAP-11
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="contracts_pending")
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    down_payment_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    installment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    product_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Set once a Murabaha contract is signed. Multiple orders (a cart's line items) may
    # share the same loan_id for unified financing — see ContractSignerService.sign_murabaha.
    loan_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("loans.id", ondelete="SET NULL"), nullable=True)

    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        "OrderStatusHistory",
        back_populates="order",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_orders_user_id_created_at", "user_id", "created_at"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_loan_id", "loan_id"),
    )


class OrderStatusHistory(Base, TimestampMixin):
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="status_history")

    __table_args__ = (
        Index("ix_order_status_history_order_id", "order_id"),
    )
