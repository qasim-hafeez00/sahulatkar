"""Add remaining ledger ORM columns missed in the first drift sweep

Revision ID: 091
Revises: 090
Create Date: 2026-08-28 00:00:00.000000

Continuation of migration 090 -- a second, more careful pass through every
model in packages/shared-python/sk_shared/models/ledger.py against the real
schema turned up two more genuinely missing columns, both live-verified by
running the real down-payment posting path end-to-end:

- `journal_entry_lines.currency` (JournalEntryLine.currency, NOT NULL
  default 'PKR') -- missing entirely; every real journal-entry-line INSERT
  failed outright with `UndefinedColumnError` until this is added.
- `ledger_account_balances.updated_at` -- `LedgerAccountBalance` inherits
  `TimestampMixin` (created_at AND updated_at), but the real table only
  ever had `created_at`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '091'
down_revision: Union[str, None] = '090'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "journal_entry_lines",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"),
    )
    op.add_column(
        "ledger_account_balances",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_column("ledger_account_balances", "updated_at")
    op.drop_column("journal_entry_lines", "currency")
