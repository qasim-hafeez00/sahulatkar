from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Loan(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    murabaha_contract_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("murabaha_contracts.id", ondelete="SET NULL"), nullable=True)
    loan_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    principal_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    profit_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total_repayable: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    down_payment_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    balance_financed: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    profit_rate_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    installment_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    installment_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    total_paid: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_outstanding: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    late_fee_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    installments: Mapped[list["Installment"]] = relationship("Installment", back_populates="loan", cascade="all, delete-orphan")
    payment_transactions: Mapped[list["PaymentTransaction"]] = relationship("PaymentTransaction", back_populates="loan", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_loans_order_id", "order_id"),
        Index("ix_loans_user_id", "user_id"),
        Index("ix_loans_murabaha_contract_id", "murabaha_contract_id"),
    )


class Installment(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "installments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("loans.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    installment_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_down_payment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    principal_portion: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    profit_portion: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    paid_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    days_overdue: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    late_fee_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    late_fee_waived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    loan: Mapped["Loan"] = relationship("Loan", back_populates="installments")
    payment_transactions: Mapped[list["PaymentTransaction"]] = relationship("PaymentTransaction", back_populates="installment")

    __table_args__ = (
        Index("ix_installments_loan_id", "loan_id"),
        Index("ix_installments_user_id", "user_id"),
        Index("ix_installments_due_date_user_id_pending", "due_date", "user_id"),
    )


class PaymentMethod(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    method_type: Mapped[str] = mapped_column(String(20), nullable=False)
    tokenized_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    masked_pan: Mapped[Optional[str]] = mapped_column(String(19), nullable=True)
    expiry_month: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    expiry_year: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    payment_transactions: Mapped[list["PaymentTransaction"]] = relationship("PaymentTransaction", back_populates="payment_method")

    __table_args__ = (
        Index("ix_payment_methods_user_id", "user_id"),
        Index("ix_payment_methods_provider_reference", "provider", "tokenized_reference"),
    )


class PaymentTransaction(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "payment_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    loan_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("loans.id", ondelete="SET NULL"), nullable=True)
    installment_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("installments.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    payment_method_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("payment_methods.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PKR")
    gateway: Mapped[str] = mapped_column(String(20), nullable=False)
    gateway_txn_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    transaction_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True) # GAP-10
    provider: Mapped[Optional[str]] = mapped_column(String(30), nullable=True) # GAP-10 (e.g. manual, system)
    gateway_response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="initiated")
    failure_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_of_txn_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("payment_transactions.id", ondelete="SET NULL"), nullable=True)
    settlement_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reconciled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    loan: Mapped[Optional["Loan"]] = relationship("Loan", back_populates="payment_transactions")
    installment: Mapped[Optional["Installment"]] = relationship("Installment", back_populates="payment_transactions")
    payment_method: Mapped[Optional["PaymentMethod"]] = relationship("PaymentMethod", back_populates="payment_transactions")
    retry_of_transaction: Mapped[Optional["PaymentTransaction"]] = relationship("PaymentTransaction", remote_side="PaymentTransaction.id")

    __table_args__ = (
        Index("ix_payment_transactions_user_id", "user_id"),
        Index("ix_payment_transactions_loan_id", "loan_id"),
        Index("ix_payment_transactions_installment_id", "installment_id"),
        Index("ix_payment_transactions_gateway_txn_id", "gateway_txn_id"),
    )


class Reconciliation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "reconciliations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gateway: Mapped[str] = mapped_column(String(30), nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    actual_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    period_key: Mapped[str] = mapped_column(String(10), nullable=False)
    reconciled_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    reconciled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    items: Mapped[list["ReconciliationItem"]] = relationship(
        "ReconciliationItem",
        back_populates="reconciliation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_reconciliations_gateway_settlement_date", "gateway", "settlement_date"),
        Index("ix_reconciliations_status", "status"),
    )


class ReconciliationItem(Base):
    __tablename__ = "reconciliation_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reconciliation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reconciliations.id", ondelete="CASCADE"), nullable=False)
    payment_txn_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("payment_transactions.id", ondelete="SET NULL"), nullable=True)
    gateway_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expected_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    actual_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    discrepancy_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    reconciliation: Mapped["Reconciliation"] = relationship("Reconciliation", back_populates="items")

    __table_args__ = (
        Index("ix_reconciliation_items_reconciliation_id", "reconciliation_id"),
        Index("ix_reconciliation_items_gateway_ref", "gateway_ref"),
    )


class VirtualCard(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "virtual_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    issuer: Mapped[str] = mapped_column(String(20), nullable=False)
    stripe_cardholder_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    issuer_card_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    masked_number: Mapped[str] = mapped_column(String(19), nullable=False)
    card_expiry: Mapped[date] = mapped_column(Date, nullable=False)
    authorized_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    loaded_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    mcc_lock: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    merchant_lock: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    charged_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    void_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    encrypted_pan: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    encrypted_cvv: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    # Versioned-key envelope scheme: records which encryption key version was used
    # to produce encrypted_pan/encrypted_cvv (e.g. "v1", "v2"), so decryption can look
    # up the correct key instead of assuming a single static one. NULL means the row
    # predates this column and must be treated as the legacy "v1" key (see
    # src/services/vcn.py _LEGACY_KEY_VERSION). New rows always populate this column.
    encryption_key_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        Index("ix_virtual_cards_order_id", "order_id"),
        Index("ix_virtual_cards_user_id", "user_id"),
        Index("ix_virtual_cards_status", "status"),
    )


class VcnKmsKeyVersion(Base, TimestampMixin):
    """Persists the AWS KMS-encrypted data key for each VCN encryption key
    version, so the plaintext data key used to encrypt a batch of PAN/CVV
    ciphertext can be rehydrated (via kms:Decrypt) by any process/pod — not
    just the one that originally called kms:GenerateDataKey.

    One row is created per version the first time that version is used to
    encrypt (see VcnKeyProvider._kms_get_cipher in
    apps/payment-orchestrator/src/services/vcn_encryption.py); `encrypted_pan`
    /`encrypted_cvv` on `virtual_cards` never store this row's contents
    directly — only the version tag, via `encryption_key_version`.
    """

    __tablename__ = "vcn_kms_key_versions"

    version: Mapped[str] = mapped_column(String(20), primary_key=True)
    kms_key_arn: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_data_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
