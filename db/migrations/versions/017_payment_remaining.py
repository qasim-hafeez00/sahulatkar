"""Payment Remaining

Revision ID: 017_payment_remaining
Revises: 016_order_remaining
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '017_payment_remaining'
down_revision: Union[str, None] = '016_order_remaining'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Update installments
    op.add_column('installments', sa.Column('late_fee_waiver_reason', sa.Text(), nullable=True))
    op.add_column('installments', sa.Column('reminders_sent', sa.SmallInteger(), nullable=False, server_default=sa.text("0")))
    op.add_column('installments', sa.Column('last_reminder_at', sa.DateTime(), nullable=True))

    # 2. Update loans
    op.add_column('loans', sa.Column('start_date', sa.Date(), nullable=True))
    op.add_column('loans', sa.Column('expected_end_date', sa.Date(), nullable=True))
    op.add_column('loans', sa.Column('actual_end_date', sa.Date(), nullable=True))
    op.add_column('loans', sa.Column('last_payment_date', sa.DateTime(), nullable=True))

    op.create_table(
        "refunds",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("payment_txn_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("refund_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=False),
        sa.Column("gateway_refund_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='initiated'),
        sa.Column("initiated_by", sa.String(length=20), nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('initiated','processing','completed','failed')"),
        sa.CheckConstraint("initiated_by IN ('user','admin','system')"),
        sa.ForeignKeyConstraint(["payment_txn_id"], ["payment_transactions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_refunds_payment_txn_id", "refunds", ["payment_txn_id"], unique=False)
    op.create_index("ix_refunds_order_id", "refunds", ["order_id"], unique=False)
    op.create_index("ix_refunds_status", "refunds", ["status"], unique=False)

    op.create_table(
        "chargebacks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("payment_txn_id", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default='open'),
        sa.Column("evidence_due_date", sa.Date(), nullable=True),
        sa.Column("resolution", sa.String(length=30), nullable=True),
        sa.Column("gateway_case_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('open','evidence_submitted','won','lost','cancelled')"),
        sa.ForeignKeyConstraint(["payment_txn_id"], ["payment_transactions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_chargebacks_payment_txn_id", "chargebacks", ["payment_txn_id"], unique=False)
    op.create_index("ix_chargebacks_status", "chargebacks", ["status"], unique=False)

    op.create_table(
        "settlements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("gateway", sa.String(length=30), nullable=False),
        sa.Column("settlement_batch_id", sa.String(length=100), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("fee_amount", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("transaction_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','matched','discrepant','reconciled')"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gateway", "settlement_batch_id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_settlements_gateway_settlement_date", "settlements", ["gateway", sa.text("settlement_date DESC")], unique=False)

    op.create_table(
        "payment_retries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("installment_id", sa.BigInteger(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("attempt_number", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("gateway_to_try", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='scheduled'),
        sa.Column("triggered_at", sa.DateTime(), nullable=True),
        sa.Column("result_txn_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('scheduled','running','succeeded','failed','cancelled')"),
        sa.ForeignKeyConstraint(["installment_id"], ["installments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["result_txn_id"], ["payment_transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_retries_installment_id", "payment_retries", ["installment_id"], unique=False)

    op.create_table(
        "payment_arrangements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("loan_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("arrangement_type", sa.String(length=30), nullable=False),
        sa.Column("new_schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approved_by_admin", sa.BigInteger(), nullable=True),
        sa.Column("shariah_compliance_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("arrangement_type IN ('extended_plan','settlement','payment_holiday')"),
        sa.CheckConstraint("status IN ('pending','approved','active','completed','rejected')"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_admin"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_payment_arrangements_loan_id", "payment_arrangements", ["loan_id"], unique=False)
    op.create_index("ix_payment_arrangements_status", "payment_arrangements", ["status"], unique=False)

    op.create_table(
        "early_payoff_discounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("loan_id", sa.BigInteger(), nullable=False),
        sa.Column("remaining_balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("discount_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("valid_until", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("shariah_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_early_payoff_discounts_loan_id", "early_payoff_discounts", ["loan_id"], unique=False)

def downgrade() -> None:
    op.drop_table("early_payoff_discounts")
    op.drop_table("payment_arrangements")
    op.drop_table("payment_retries")
    op.drop_table("settlements")
    op.drop_table("chargebacks")
    op.drop_table("refunds")

    op.drop_column('loans', 'last_payment_date')
    op.drop_column('loans', 'actual_end_date')
    op.drop_column('loans', 'expected_end_date')
    op.drop_column('loans', 'start_date')

    op.drop_column('installments', 'last_reminder_at')
    op.drop_column('installments', 'reminders_sent')
    op.drop_column('installments', 'late_fee_waiver_reason')
