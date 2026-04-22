from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(slots=True, frozen=True)
class PostingLine:
    account_code: str
    debit_amount: Decimal = Decimal("0.00")
    credit_amount: Decimal = Decimal("0.00")
    description: str | None = None

    def __post_init__(self) -> None:
        if self.debit_amount < 0 or self.credit_amount < 0:
            raise ValueError("Amounts cannot be negative")
        if self.debit_amount > 0 and self.credit_amount > 0:
            raise ValueError("A single line cannot have both debit and credit amounts")
        if self.debit_amount == 0 and self.credit_amount == 0:
            raise ValueError("Line must have either a debit or credit amount")


def assert_balanced(lines: Iterable[PostingLine]) -> tuple[Decimal, Decimal]:
    """
    Assert that the sum of debits equals the sum of credits.
    Returns the total debit/credit amount if balanced.
    """
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    
    for line in lines:
        total_debit += line.debit_amount
        total_credit += line.credit_amount
        
    if total_debit != total_credit:
        raise ValueError(f"JOURNAL_ENTRY_NOT_BALANCED: Total Debit ({total_debit}) != Total Credit ({total_credit})")
    
    if total_debit == 0:
        raise ValueError("JOURNAL_ENTRY_ZERO_AMOUNT: Entry must have a non-zero total")
        
    return total_debit, total_credit


async def generate_entry_number(session, entry_date) -> str:
    # Fetch next sequence value with dialect fallback for tests
    try:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            result = await session.execute(text("SELECT nextval('journal_entry_number_seq')"))
            seq_val = result.scalar()
            entry_number = f"JE-{entry_date.strftime('%Y%m')}-{seq_val:06d}"
        else:
            # Fallback for SQLite/tests
            from uuid import uuid4
            entry_number = f"JE-{entry_date.strftime('%Y%m')}-{uuid4().hex[:6].upper()}"
    except Exception:
        # Emergency fallback if bind/dialect check fails
        from uuid import uuid4
        entry_number = f"JE-{entry_date.strftime('%Y%m')}-{uuid4().hex[:6].upper()}"
    return entry_number


def validate_entry_metadata(entry_type: str, source_type: str, source_id: int | str) -> None:
    """Validate journal entry metadata."""
    if not entry_type:
        raise ValueError("entry_type is required")
    if not source_type:
        raise ValueError("source_type is required")
    if source_id is None or source_id == "":
        raise ValueError("source_id is required")
