from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class LedgerAccount(Base, TimestampMixin):
    __tablename__ = "ledger_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    normal_balance: Mapped[str] = mapped_column(String(6), nullable=False)
    parent_account_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ledger_accounts.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    journal_lines: Mapped[list["JournalEntryLine"]] = relationship("JournalEntryLine", back_populates="account")


class JournalEntry(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    is_balanced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_debit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_credit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    lines: Mapped[list["JournalEntryLine"]] = relationship(
        "JournalEntryLine",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_journal_entries_entry_date", "entry_date"),
        Index("ix_journal_entries_source", "source_type", "source_id"),
        UniqueConstraint("source_type", "source_id", name="uq_journal_entries_source"),
    )


class JournalEntryLine(Base, TimestampMixin):
    __tablename__ = "journal_entry_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    journal_id: Mapped[int] = mapped_column(Integer, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("ledger_accounts.id", ondelete="RESTRICT"), nullable=False)
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    journal_entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
    account: Mapped["LedgerAccount"] = relationship("LedgerAccount", back_populates="journal_lines")

    __table_args__ = (
        Index("ix_journal_entry_lines_journal_id", "journal_id"),
        Index("ix_journal_entry_lines_account_id", "account_id"),
    )


class CharityOrganization(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "charity_organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bank_iban: Mapped[str] = mapped_column(String(34), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(100), nullable=False)
    approved_by_shariah_board: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    allocations: Mapped[list["LateFeeCharityAllocation"]] = relationship("LateFeeCharityAllocation", back_populates="charity_org")

    __table_args__ = (
        UniqueConstraint("registration_number", name="uq_charity_organization_registration_number"),
        UniqueConstraint("bank_iban", name="uq_charity_organization_bank_iban"),
    )


class LateFeeCharityAllocation(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "late_fee_charity_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    installment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("installments.id", ondelete="CASCADE"), nullable=False)
    loan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("loans.id", ondelete="CASCADE"), nullable=False)
    late_fee_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    charity_org_id: Mapped[int] = mapped_column(Integer, ForeignKey("charity_organizations.id", ondelete="RESTRICT"), nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    disbursed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    receipt_s3: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    charity_org: Mapped["CharityOrganization"] = relationship("CharityOrganization", back_populates="allocations")

    __table_args__ = (
        Index("ix_late_fee_charity_allocations_installment_id", "installment_id"),
        Index("ix_late_fee_charity_allocations_charity_org_id", "charity_org_id"),
        UniqueConstraint("installment_id", name="uq_late_fee_charity_allocations_installment_id"),
    )