from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(slots=True, frozen=True)
class PostingLine:
    account_code: str
    debit_amount: Decimal = Decimal("0.00")
    credit_amount: Decimal = Decimal("0.00")
    currency: str = "PKR"
    description: str | None = None

    def __post_init__(self) -> None:
        if self.debit_amount < 0 or self.credit_amount < 0:
            raise ValueError("Amounts cannot be negative")
        if self.debit_amount > 0 and self.credit_amount > 0:
            raise ValueError("A single line cannot have both debit and credit amounts")
        if self.debit_amount == 0 and self.credit_amount == 0:
            raise ValueError("Line must have either a debit or credit amount")
        if not self.currency or len(self.currency) != 3:
            raise ValueError("Invalid currency code")


def assert_balanced(lines: Iterable[PostingLine]) -> tuple[Decimal, Decimal, str]:
    """
    Assert that the sum of debits equals the sum of credits and currencies match.
    Returns the total debit/credit amount and currency if balanced.
    """
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    entry_currency: str | None = None
    
    for line in lines:
        if entry_currency is None:
            entry_currency = line.currency
        elif line.currency != entry_currency:
            # SahulatKar P1: Ledger entries must be single-currency for now.
            # Multi-currency entries require an FX settlement line or a complex balancing engine.
            raise ValueError(f"MULTI_CURRENCY_ENTRY_NOT_SUPPORTED: {line.currency} vs {entry_currency}")
            
        total_debit += line.debit_amount
        total_credit += line.credit_amount
        
    if total_debit != total_credit:
        raise ValueError(f"JOURNAL_ENTRY_NOT_BALANCED: Total Debit ({total_debit}) != Total Credit ({total_credit})")
    
    if total_debit == 0:
        raise ValueError("JOURNAL_ENTRY_ZERO_AMOUNT: Entry must have a non-zero total")
        
    return total_debit, total_credit, entry_currency or "PKR"


def validate_entry_metadata(entry_type: str, source_type: str, source_id: int | str) -> None:
    """Validate journal entry metadata."""
    if not entry_type:
        raise ValueError("entry_type is required")
    if not source_type:
        raise ValueError("source_type is required")
    if source_id is None or source_id == "":
        raise ValueError("source_id is required")
