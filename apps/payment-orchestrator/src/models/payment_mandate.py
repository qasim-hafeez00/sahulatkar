from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from sk_shared.models.base import Base, TimestampMixin, UUIDMixin


class PaymentMandate(Base, UUIDMixin, TimestampMixin):
    """
    Stores authorization for recurring auto-debits (mandates).
    Essential for Raast (SBP-authorized recurring IBFT) and JazzCash direct charge.
    """
    __tablename__ = "payment_mandates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gateway: Mapped[str] = mapped_column(String(20), nullable=False)  # raast, jazzcash
    mandate_reference: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active, expired, revoked
    
    # Financial constraints
    max_amount_per_txn: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PKR")
    
    # Metadata for the gateway
    payer_identifier: Mapped[str] = mapped_column(String(255), nullable=False)  # IBAN or Phone
    
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_valid(self, amount: Decimal) -> bool:
        if self.status != "active":
            return False
        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
            return False
        if self.max_amount_per_txn and amount > self.max_amount_per_txn:
            return False
        return True
