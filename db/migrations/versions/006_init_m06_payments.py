"""Init M06 payments

Revision ID: 006_init_m06_payments
Revises: 005_harden_m05_contracts
Create Date: 2026-04-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_init_m06_payments"
down_revision: Union[str, None] = "005_harden_m05_contracts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Orders and Order Status History
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'contracts_pending'")),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("down_payment_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("product_description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_orders_user_id_created_at", "orders", ["user_id", "created_at"], unique=False)
    op.create_index("ix_orders_status", "orders", ["status"], unique=False)

    op.create_table(
        "order_status_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("from_status", sa.String(length=50), nullable=True),
        sa.Column("to_status", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_status_history_order_id", "order_status_history", ["order_id"], unique=False)

    # 1. Loans table
    op.create_table(
        "loans",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("murabaha_contract_id", sa.BigInteger(), nullable=True),
        sa.Column("loan_number", sa.String(length=30), nullable=False),
        sa.Column("principal_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("profit_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_repayable", sa.Numeric(14, 2), nullable=False),
        sa.Column("down_payment_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_financed", sa.Numeric(14, 2), nullable=False),
        sa.Column("profit_rate_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("plan_type", sa.String(length=20), nullable=False),
        sa.Column("installment_count", sa.SmallInteger(), nullable=False),
        sa.Column("installment_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("total_paid", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("total_outstanding", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("late_fee_total", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["murabaha_contract_id"], ["murabaha_contracts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("loan_number"),
    )
    op.create_index("ix_loans_order_id", "loans", ["order_id"], unique=False)
    op.create_index("ix_loans_user_id", "loans", ["user_id"], unique=False)
    op.create_index("ix_loans_murabaha_contract_id", "loans", ["murabaha_contract_id"], unique=False)

    op.create_table(
        "installments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("loan_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("installment_number", sa.SmallInteger(), nullable=False),
        sa.Column("is_down_payment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("principal_portion", sa.Numeric(14, 2), nullable=False),
        sa.Column("profit_portion", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("days_overdue", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("late_fee_amount", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("late_fee_waived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_installments_loan_id", "installments", ["loan_id"], unique=False)
    op.create_index("ix_installments_user_id", "installments", ["user_id"], unique=False)
    op.create_index("ix_installments_due_date_user_id_pending", "installments", ["due_date", "user_id"], unique=False)

    op.create_table(
        "payment_methods",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("method_type", sa.String(length=20), nullable=False),
        sa.Column("tokenized_reference", sa.String(length=255), nullable=False),
        sa.Column("masked_pan", sa.String(length=19), nullable=True),
        sa.Column("expiry_month", sa.String(length=2), nullable=True),
        sa.Column("expiry_year", sa.String(length=4), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_payment_methods_user_id", "payment_methods", ["user_id"], unique=False)
    op.create_index("ix_payment_methods_provider_reference", "payment_methods", ["provider", "tokenized_reference"], unique=False)

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("loan_id", sa.BigInteger(), nullable=True),
        sa.Column("installment_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_method_id", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'PKR'")),
        sa.Column("gateway", sa.String(length=20), nullable=False),
        sa.Column("gateway_txn_id", sa.String(length=255), nullable=True),
        sa.Column("gateway_response", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'initiated'")),
        sa.Column("failure_code", sa.String(length=50), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("retry_of_txn_id", sa.BigInteger(), nullable=True),
        sa.Column("settlement_id", sa.BigInteger(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["installment_id"], ["installments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payment_method_id"], ["payment_methods.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["retry_of_txn_id"], ["payment_transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_payment_transactions_user_id", "payment_transactions", ["user_id"], unique=False)
    op.create_index("ix_payment_transactions_loan_id", "payment_transactions", ["loan_id"], unique=False)
    op.create_index("ix_payment_transactions_installment_id", "payment_transactions", ["installment_id"], unique=False)
    op.create_index("ix_payment_transactions_gateway_txn_id", "payment_transactions", ["gateway_txn_id"], unique=False)

    op.create_table(
        "virtual_cards",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("issuer", sa.String(length=20), nullable=False),
        sa.Column("issuer_card_id", sa.String(length=255), nullable=False),
        sa.Column("masked_number", sa.String(length=19), nullable=False),
        sa.Column("card_expiry", sa.Date(), nullable=False),
        sa.Column("authorized_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("loaded_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("mcc_lock", sa.String(length=10), nullable=True),
        sa.Column("merchant_lock", sa.String(length=255), nullable=True),
        sa.Column("charged_amount", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("void_reason", sa.String(length=100), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("encrypted_pan", sa.LargeBinary(), nullable=True),
        sa.Column("encrypted_cvv", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("order_id"),
        sa.UniqueConstraint("issuer_card_id"),
    )
    op.create_index("ix_virtual_cards_order_id", "virtual_cards", ["order_id"], unique=False)
    op.create_index("ix_virtual_cards_user_id", "virtual_cards", ["user_id"], unique=False)
    op.create_index("ix_virtual_cards_status", "virtual_cards", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_order_status_history_order_id", table_name="order_status_history")
    op.drop_table("order_status_history")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_user_id_created_at", table_name="orders")
    op.drop_table("orders")

    op.drop_index("ix_virtual_cards_status", table_name="virtual_cards")
    op.drop_index("ix_virtual_cards_user_id", table_name="virtual_cards")
    op.drop_index("ix_virtual_cards_order_id", table_name="virtual_cards")
    op.drop_table("virtual_cards")

    op.drop_index("ix_payment_transactions_gateway_txn_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_installment_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_loan_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_user_id", table_name="payment_transactions")
    op.drop_table("payment_transactions")

    op.drop_index("ix_payment_methods_provider_reference", table_name="payment_methods")
    op.drop_index("ix_payment_methods_user_id", table_name="payment_methods")
    op.drop_table("payment_methods")

    op.drop_index("ix_installments_due_date_user_id_pending", table_name="installments")
    op.drop_index("ix_installments_user_id", table_name="installments")
    op.drop_index("ix_installments_loan_id", table_name="installments")
    op.drop_table("installments")

    op.drop_index("ix_loans_murabaha_contract_id", table_name="loans")
    op.drop_index("ix_loans_user_id", table_name="loans")
    op.drop_index("ix_loans_order_id", table_name="loans")
    op.drop_table("loans")