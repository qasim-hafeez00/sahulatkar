"""Fix ledger_account_balances numeric precision drift: NUMERIC(18,2) -> NUMERIC(14,2)

Revision ID: 073
Revises: 072
Create Date: 2026-07-08 00:00:00.000000

Migration 047 created `ledger_account_balances.debit_balance/credit_balance/
net_balance` as `NUMERIC(18, 2)`, while the `LedgerAccountBalance` ORM model
(`sk_shared.models.ledger`) has always mapped these columns as
`Numeric(14, 2)` -- and every other money column in this service
(`journal_entries.total_debit/total_credit`,
`journal_entry_lines.debit_amount/credit_amount`,
`late_fee_charity_allocations.late_fee_amount`, ...) already uses the
service-wide `DECIMAL(14, 2)` convention. `NUMERIC(18, 2)` allows values up
to ~10^16, far beyond any realistic PKR ledger balance and inconsistent with
every other money column in the same table's own account/journal-entry
tables it's meant to summarize.

Narrowing NUMERIC(18,2) -> NUMERIC(14,2) is safe here: the practical range of
PKR ledger balances (the platform's chart of accounts, order amounts, and
loan sizes are all well under a billion PKR) is nowhere close to
NUMERIC(14,2)'s ~10^12 ceiling, so no existing snapshot value can be out of
range.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '073'
down_revision: Union[str, None] = '072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("debit_balance", "credit_balance", "net_balance")


def upgrade() -> None:
    for column in _COLUMNS:
        op.alter_column(
            "ledger_account_balances",
            column,
            type_=sa.Numeric(14, 2),
            existing_type=sa.Numeric(18, 2),
            existing_nullable=False,
            existing_server_default=sa.text("0"),
        )


def downgrade() -> None:
    for column in _COLUMNS:
        op.alter_column(
            "ledger_account_balances",
            column,
            type_=sa.Numeric(18, 2),
            existing_type=sa.Numeric(14, 2),
            existing_nullable=False,
            existing_server_default=sa.text("0"),
        )
