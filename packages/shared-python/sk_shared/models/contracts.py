from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin, SoftDeleteMixin


class WakalahAgreement(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "wakalah_agreements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    contract_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    authorized_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    contract_pdf_path: Mapped[str] = mapped_column(Text, nullable=False)
    contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    otp_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Principal (Customer) Details for Legal Validity
    principal_name: Mapped[str] = mapped_column(String(200), nullable=True)  # Cleartext fallback / display
    # SEC-10: AES-256 encrypted full name (KMSProvider) — preferred over cleartext principal_name
    principal_name_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    principal_cnic: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    principal_phone: Mapped[str] = mapped_column(String(20), nullable=True)
    
    # Agent (SahulatKar) Details
    agent_name: Mapped[str] = mapped_column(String(100), default="SahulatKar (Pvt) Ltd.", nullable=False)
    agent_secp_license: Mapped[str] = mapped_column(String(50), default="SECP-L-12345", nullable=False)
    
    # Product/Transaction Metadata (Snapshot for Immutability)
    product_description: Mapped[str] = mapped_column(Text, nullable=True)
    merchant_name: Mapped[str] = mapped_column(String(255), nullable=True)
    product_url: Mapped[str] = mapped_column(String(2048), nullable=True)
    price_variance_pct: Mapped[float] = mapped_column(Numeric(4, 2), default=5.00, nullable=False)

    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # The physical table already had these (DB has them, model didn't map
    # them) — src/services/delivery_events.py's apply_delivery_confirmed_
    # envelope sets wakalah.is_executed/.executed_at on delivery, but as
    # unmapped attributes those assignments were silently dropped on
    # commit; is_executed stayed false forever regardless of delivery
    # status. Live-tested: fixed once these were added as real columns.
    is_executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    signatures: Mapped[list["ContractDigitalSignature"]] = relationship(
        "ContractDigitalSignature",
        back_populates="wakalah_agreement",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_wakalah_order_id", "order_id"),
        Index("ix_wakalah_user_id", "user_id"),
    )


class MurabahaContract(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "murabaha_contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    wakalah_agreement_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("wakalah_agreements.id", ondelete="SET NULL"),
        nullable=True,
    )
    contract_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    cost_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    profit_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    profit_rate_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    total_sale_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="PKR", nullable=False)
    
    installment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    installment_schedule: Mapped[dict] = mapped_column(JSON, nullable=False)
    contract_pdf_path: Mapped[str] = mapped_column(Text, nullable=False)
    contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    otp_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    
    template_version: Mapped[str] = mapped_column(String(10), default="1.0", nullable=False)
    validated_by_shariah_board: Mapped[bool] = mapped_column(default=False, nullable=False)
    
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    signatures: Mapped[list["ContractDigitalSignature"]] = relationship(
        "ContractDigitalSignature",
        back_populates="murabaha_contract",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_murabaha_order_id", "order_id"),
        Index("ix_murabaha_user_id", "user_id"),
    )


class ShariahBoardApproval(Base, TimestampMixin):
    """Backing record for MurabahaContract.validated_by_shariah_board.

    HIGH fix: validated_by_shariah_board used to be hardcoded True on every
    generated contract with no approval record anywhere in the codebase --
    a compliance-integrity gap (the field claimed a real board sign-off that
    never happened). This is the minimal structurally-honest fix: an admin
    records here which contract template_version the Shariah board has
    actually approved (see api/v1/admin_compliance.py's
    POST /admin/compliance/shariah-board-approvals), and
    ContractGeneratorService.generate_murabaha checks "is the
    template_version I'm about to stamp on this contract in the approved
    set?" before setting the flag -- True only for an approved version,
    False (with a logged warning) for anything unapproved/unknown.
    """
    __tablename__ = "shariah_board_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_version: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    approved_by: Mapped[str] = mapped_column(String(200), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ContractDigitalSignature(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "contract_digital_signatures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wakalah_agreement_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("wakalah_agreements.id", ondelete="CASCADE"),
        nullable=True,
    )
    murabaha_contract_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("murabaha_contracts.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    signature_type: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    otp_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    wakalah_agreement: Mapped[Optional["WakalahAgreement"]] = relationship(
        "WakalahAgreement",
        back_populates="signatures",
    )
    murabaha_contract: Mapped[Optional["MurabahaContract"]] = relationship(
        "MurabahaContract",
        back_populates="signatures",
    )

    __table_args__ = (
        Index("ix_contract_signature_user_id", "user_id"),
    )
