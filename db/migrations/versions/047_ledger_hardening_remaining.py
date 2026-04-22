"""Ledger hardening remaining items.

Revision ID: 047_ledger_hardening_remaining
Revises: 046_add_ledger_periods_table
Create Date: 2026-04-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '047_ledger_hardening_remaining'
down_revision: Union[str, None] = '046_add_ledger_periods_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create ledger_account_balances table
    op.create_table(
        "ledger_account_balances",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("period_key", sa.String(length=10), nullable=True),
        sa.Column("debit_balance", sa.Numeric(18, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("credit_balance", sa.Numeric(18, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("net_balance", sa.Numeric(18, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["ledger_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["period_key"], ["ledger_periods.period_key"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "snapshot_date", name="uq_ledger_account_balances_account_date"),
    )
    op.create_index("ix_ledger_account_balances_snapshot_date", "ledger_account_balances", ["snapshot_date"], unique=False)

    # 2. Add period_key to journal_entries
    op.add_column("journal_entries", sa.Column("period_key", sa.String(length=10), nullable=True))
    op.create_foreign_key(
        "fk_journal_entries_period_key",
        "journal_entries",
        "ledger_periods",
        ["period_key"],
        ["period_key"],
        ondelete="RESTRICT"
    )

    # 3. Add immutability check (prevent soft-deletion)
    op.create_check_constraint(
        "ck_journal_entries_immutable",
        "journal_entries",
        "deleted_at IS NULL"
    )

    # 4. Create sequence for sequential entry numbers
    op.execute("CREATE SEQUENCE IF NOT EXISTS journal_entry_number_seq")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS journal_entry_number_seq")
    op.drop_constraint("ck_journal_entries_immutable", "journal_entries", type_="check")
    op.drop_constraint("fk_journal_entries_period_key", "journal_entries", type_="foreignkey")
    op.drop_column("journal_entries", "period_key")
    op.drop_index("ix_ledger_account_balances_snapshot_date", table_name="ledger_account_balances")
    op.drop_table("ledger_account_balances")
