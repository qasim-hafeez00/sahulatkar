"""Add ledger periods table for period closing lifecycle.

Revision ID: 046_add_ledger_periods_table
Revises: 045_product_service_enhancements
Create Date: 2026-04-22 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "046_add_ledger_periods_table"
down_revision: Union[str, None] = "045_product_service_enhancements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ledger_periods",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("period_key", sa.String(length=10), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default=sa.text("'open'")),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("closed_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_ledger_periods_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period_key", name="uq_ledger_periods_period_key"),
    )
    op.create_index("ix_ledger_periods_period_key", "ledger_periods", ["period_key"], unique=False)
    op.create_index("ix_ledger_periods_status", "ledger_periods", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ledger_periods_status", table_name="ledger_periods")
    op.drop_index("ix_ledger_periods_period_key", table_name="ledger_periods")
    op.drop_table("ledger_periods")
