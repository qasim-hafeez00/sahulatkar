"""Fix ledger schema/ORM drift: journal_entries.period_key, ledger_account_balances.currency

Revision ID: 070
Revises: 069
Create Date: 2026-07-06 00:00:00.000000

Three drifts between this migration chain and the ORM models it's supposed
to back:

1. Migration 047 added journal_entries.period_key as nullable, but the
   JournalEntry model maps it as nullable=False. AccountingService.
   record_manual_entry always resolves period_key via ensure_period_open()
   before insert, so the column is in practice always populated — this
   backfills any stray NULLs (none expected) and tightens the column to
   match the ORM's real invariant.
2. Migration 047 never added a `currency` column to ledger_account_balances
   at all, even though the LedgerAccountBalance model has always mapped one
   (nullable=False, default "PKR") and BalanceService.create_snapshot has
   always inserted one. Every snapshot insert against a real Postgres
   database would fail with "column does not exist" — masked in tests
   because they build the schema from Base.metadata.create_all(), not this
   migration chain.
3. BalanceService.create_snapshot looks up existing snapshots by
   (account_id, snapshot_date, currency), but the unique constraint this
   migration chain created only covers (account_id, snapshot_date), and
   under a different name than the ORM's uq_ledger_account_balance_date.
   Fixed by dropping the old constraint and creating the 3-column one under
   the name the ORM expects.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '070'
down_revision: Union[str, None] = '069'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ledger_account_balances.currency drift ---
    op.add_column(
        "ledger_account_balances",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"),
    )
    op.drop_constraint(
        "uq_ledger_account_balances_account_date", "ledger_account_balances", type_="unique"
    )
    op.create_unique_constraint(
        "uq_ledger_account_balance_date",
        "ledger_account_balances",
        ["account_id", "snapshot_date", "currency"],
    )

    # --- journal_entries.period_key drift ---
    # Backfill any historical rows a NULL period_key (none expected on a
    # correctly-operating system, since the app always resolves one before
    # insert) and make sure a matching ledger_periods row exists for the FK.
    op.execute(
        """
        INSERT INTO ledger_periods (period_key, fiscal_year, start_date, end_date, status, created_at, updated_at)
        SELECT DISTINCT
            to_char(je.entry_date, 'YYYY-MM'),
            EXTRACT(YEAR FROM je.entry_date)::int,
            date_trunc('month', je.entry_date)::date,
            (date_trunc('month', je.entry_date) + INTERVAL '1 month - 1 day')::date,
            'closed',
            now(),
            now()
        FROM journal_entries je
        WHERE je.period_key IS NULL
        ON CONFLICT (period_key) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE journal_entries
        SET period_key = to_char(entry_date, 'YYYY-MM')
        WHERE period_key IS NULL
        """
    )
    op.alter_column("journal_entries", "period_key", nullable=False)

    # --- DB-level double-entry balance constraint (defense-in-depth on top
    # of the existing app-level assert_balanced()) ---
    op.create_check_constraint(
        "chk_journal_entries_balanced",
        "journal_entries",
        "total_debit = total_credit",
    )


def downgrade() -> None:
    op.drop_constraint("chk_journal_entries_balanced", "journal_entries", type_="check")
    op.alter_column("journal_entries", "period_key", nullable=True)
    op.drop_constraint("uq_ledger_account_balance_date", "ledger_account_balances", type_="unique")
    op.create_unique_constraint(
        "uq_ledger_account_balances_account_date",
        "ledger_account_balances",
        ["account_id", "snapshot_date"],
    )
    op.drop_column("ledger_account_balances", "currency")
