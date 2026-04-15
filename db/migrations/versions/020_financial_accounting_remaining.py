"""Financial Accounting Remaining

Revision ID: 020_financial_accounting_remaining
Revises: 019_shariah_remaining
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '020_financial_accounting_remaining'
down_revision: Union[str, None] = '019_shariah_remaining'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "reconciliations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("gateway", sa.String(length=30), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("expected_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("actual_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("discrepancy", sa.Numeric(14, 2), sa.Computed("actual_amount - expected_amount", persisted=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='open'),
        sa.Column("reconciled_by", sa.BigInteger(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('open','matched','discrepant','resolved')"),
        sa.ForeignKeyConstraint(["reconciled_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_reconciliations_gateway_settlement_date", "reconciliations", ["gateway", sa.text("settlement_date DESC")], unique=False)
    op.create_index("ix_reconciliations_status", "reconciliations", ["status"], unique=False)

    op.create_table(
        "reconciliation_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("reconciliation_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_txn_id", sa.BigInteger(), nullable=True),
        sa.Column("gateway_ref", sa.String(length=255), nullable=True),
        sa.Column("expected_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("actual_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column("discrepancy_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','matched','unmatched','discrepant')"),
        sa.ForeignKeyConstraint(["payment_txn_id"], ["payment_transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reconciliation_id"], ["reconciliations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reconciliation_items_reconciliation_id", "reconciliation_items", ["reconciliation_id"], unique=False)
    op.create_index("ix_reconciliation_items_gateway_ref", "reconciliation_items", ["gateway_ref"], unique=False)

    op.create_table(
        "revenue_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("revenue_type", sa.String(length=30), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=True),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("recognized_at", sa.DateTime(), nullable=False),
        sa.Column("journal_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("revenue_type IN ('murabaha_profit','affiliate_commission','late_fee','consumer_fee')"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_revenue_transactions_type_recognized_at", "revenue_transactions", ["revenue_type", sa.text("recognized_at DESC")], unique=False)
    op.create_index("ix_revenue_transactions_source", "revenue_transactions", ["source_type", "source_id"], unique=False)

    op.create_table(
        "gateway_settlements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("gateway", sa.String(length=30), nullable=False),
        sa.Column("settlement_batch_id", sa.String(length=100), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("fee_amount", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("transaction_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("file_s3", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gateway", "settlement_batch_id"),
    )
    op.create_index("ix_gateway_settlements_gateway_settlement_date", "gateway_settlements", ["gateway", sa.text("settlement_date DESC")], unique=False)

    op.create_table(
        "financial_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("data_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pdf_s3", sa.String(length=512), nullable=True),
        sa.Column("generated_by", sa.BigInteger(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("report_type IN ('monthly_pl','quarterly_bs','secp_bnpl_return','shariah_quarterly','tax_annual')"),
        sa.ForeignKeyConstraint(["generated_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_financial_reports_type_period_start", "financial_reports", ["report_type", sa.text("period_start DESC")], unique=False)


def downgrade() -> None:
    op.drop_table("financial_reports")
    op.drop_table("gateway_settlements")
    op.drop_table("revenue_transactions")
    op.drop_table("reconciliation_items")
    op.drop_table("reconciliations")
