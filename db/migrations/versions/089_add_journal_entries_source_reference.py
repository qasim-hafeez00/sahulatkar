"""Add missing journal_entries columns: source_reference, currency, reversed_by_id

Revision ID: 089
Revises: 088
Create Date: 2026-08-28 00:00:00.000000

`JournalEntry` (packages/shared-python/sk_shared/models/ledger.py:30-46)
declares `source_reference`, `currency`, and `reversed_by_id` -- none of the
three were ever added to the real `journal_entries` table by any migration
(confirmed directly against a fully-migrated real Postgres instance's
`\\d journal_entries`, and by grepping every migration file: the only
"source_reference"/"currency" hits anywhere are unrelated tables). Any
`SELECT` that lists all of `JournalEntry`'s mapped columns -- e.g.
`GET /entries` in apps/ledger-service/src/api/v1/entries.py, used by
AccountingService.list_journal_entries -- fails outright with
`UndefinedColumnError`. Found live-running the real order-lifecycle E2E
test end-to-end against real Postgres.

`currency` gets the same NOT NULL DEFAULT 'PKR' the model declares
(matching `ledger_accounts.currency` in the same file, which the real
table does carry). `source_reference` and `reversed_by_id` are nullable on
the model, so no backfill/default is needed for existing rows.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '089'
down_revision: Union[str, None] = '088'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "journal_entries",
        sa.Column("source_reference", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"),
    )
    op.add_column(
        "journal_entries",
        sa.Column("reversed_by_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_journal_entries_reversed_by_id",
        "journal_entries", "journal_entries",
        ["reversed_by_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_journal_entries_reversed_by_id", "journal_entries", type_="foreignkey")
    op.drop_column("journal_entries", "reversed_by_id")
    op.drop_column("journal_entries", "currency")
    op.drop_column("journal_entries", "source_reference")
