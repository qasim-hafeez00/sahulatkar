"""Add every remaining ledger ORM column missing from the real schema

Revision ID: 090
Revises: 089
Create Date: 2026-08-28 00:00:00.000000

Found live-running the real order-lifecycle E2E test end-to-end: after
fixing journal_entries' missing columns (migration 089), the exact same
class of drift kept surfacing table by table as more of the ledger code
path actually executed against real Postgres for the first time. Rather
than continue fixing these one crash at a time, this migration is the
result of directly diffing every model in packages/shared-python/sk_shared/
models/ledger.py against a fully-migrated real Postgres schema
(`\\d <table>` for each), to close out this whole class of drift in one
pass:

- `ledger_accounts` (LedgerAccount): missing `parent_code`, `account_group`,
  `currency`, `is_control`. `PeriodService`/`AccountingService` don't
  currently read these, but any future code that does (or a raw
  `SELECT * FROM ledger_accounts` / `select(LedgerAccount)`) would hit the
  same `UndefinedColumnError` class of failure this migration is closing
  out elsewhere.
- `ledger_periods` (LedgerPeriod): missing `fiscal_year` (NOT NULL on the
  model -- backfilled from `start_date`'s year for any pre-existing rows
  before the NOT NULL constraint is applied), `pre_close_snapshot_at`,
  `reopened_at`, `reopened_by`. This is the one that actually broke the
  E2E run: `PeriodService`, used by every `AccountingService._create_
  balanced_entry` call (i.e. every real journal posting), selects the full
  `LedgerPeriod` row and failed outright on `fiscal_year`.
- `late_fee_charity_allocations` (LateFeeCharityAllocation): missing
  `journal_entry_id` (FK to journal_entries, nullable) -- links a charity
  allocation back to the journal entry that posted it, for audit
  traceability of the late-fee-to-charity flow.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '090'
down_revision: Union[str, None] = '089'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ledger_accounts
    op.add_column("ledger_accounts", sa.Column("parent_code", sa.String(length=20), nullable=True))
    op.create_foreign_key(
        "fk_ledger_accounts_parent_code",
        "ledger_accounts", "ledger_accounts",
        ["parent_code"], ["account_code"],
        ondelete="SET NULL",
    )
    op.add_column("ledger_accounts", sa.Column("account_group", sa.String(length=100), nullable=True))
    op.add_column("ledger_accounts", sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"))
    op.add_column("ledger_accounts", sa.Column("is_control", sa.Boolean(), nullable=False, server_default=sa.false()))

    # ledger_periods
    op.add_column("ledger_periods", sa.Column("fiscal_year", sa.Integer(), nullable=True))
    op.execute("UPDATE ledger_periods SET fiscal_year = EXTRACT(YEAR FROM start_date)::integer WHERE fiscal_year IS NULL")
    op.alter_column("ledger_periods", "fiscal_year", nullable=False)
    op.add_column("ledger_periods", sa.Column("pre_close_snapshot_at", sa.DateTime(), nullable=True))
    op.add_column("ledger_periods", sa.Column("reopened_at", sa.DateTime(), nullable=True))
    op.add_column("ledger_periods", sa.Column("reopened_by", sa.String(length=100), nullable=True))

    # late_fee_charity_allocations
    op.add_column(
        "late_fee_charity_allocations",
        sa.Column("journal_entry_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_late_fee_charity_allocations_journal_entry_id",
        "late_fee_charity_allocations", "journal_entries",
        ["journal_entry_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_late_fee_charity_allocations_journal_entry_id",
        "late_fee_charity_allocations", type_="foreignkey",
    )
    op.drop_column("late_fee_charity_allocations", "journal_entry_id")

    op.drop_column("ledger_periods", "reopened_by")
    op.drop_column("ledger_periods", "reopened_at")
    op.drop_column("ledger_periods", "pre_close_snapshot_at")
    op.drop_column("ledger_periods", "fiscal_year")

    op.drop_column("ledger_accounts", "is_control")
    op.drop_column("ledger_accounts", "currency")
    op.drop_column("ledger_accounts", "account_group")
    op.drop_constraint("fk_ledger_accounts_parent_code", "ledger_accounts", type_="foreignkey")
    op.drop_column("ledger_accounts", "parent_code")
