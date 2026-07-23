"""Reconcile loans/installments/payment_transactions with current payment models

Revision ID: 057
Revises: 056
Create Date: 2026-07-03 00:00:05.000000

Same class of drift as 052/053/054/055/056, on the loan/payment side:

  - loans / installments: missing `deleted_at` (SoftDeleteMixin) — every
    lookup in this codebase filters `.deleted_at.is_(None)`, so loan/
    installment reads have been failing outright. `loans.start_date` /
    `expected_end_date` are NOT NULL with no default, but nothing in the
    current code populates them (an older schema's fields). Also,
    `chk_loans_plan_type` only allows `pay_in_3/4/6/pay_full` — the current
    contract signer always inserts `plan_type='murabaha'`, and
    `chk_loans_installment_count` caps at 6 even though 12-month plans are a
    supported product option (settings.PROFIT_RATES has a "12" tier) — both
    constraints predate the current Murabaha product design and reject every
    real loan insert.
  - payment_transactions: missing `loan_id` (needed to resolve a cart's shared
    Loan — see 051/gateway loan-aggregation logic), `updated_at`/`deleted_at`
    (Timestamp/SoftDeleteMixin), and `transaction_type`/`provider` (GAP-10,
    used everywhere down-payment/installment transactions are created).
    `installment_id` is NOT NULL, but down-payment transactions are
    order/loan-level and have no installment. `chk_ptxn_status` doesn't
    include 'confirmed' even though PaymentConfirmedPayload / the internal
    confirmation callback use "confirmed"/"failed" as the two valid values.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '057'
down_revision: Union[str, None] = '056'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- loans ---
    op.add_column("loans", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("loans", "start_date", nullable=True)
    op.alter_column("loans", "expected_end_date", nullable=True)
    op.drop_constraint("chk_loans_plan_type", "loans", type_="check")
    op.create_check_constraint(
        "chk_loans_plan_type", "loans",
        "plan_type IN ('pay_in_3', 'pay_in_4', 'pay_in_6', 'pay_full', 'murabaha')",
    )
    op.drop_constraint("chk_loans_installment_count", "loans", type_="check")
    op.create_check_constraint(
        "chk_loans_installment_count", "loans",
        "installment_count >= 1 AND installment_count <= 12",
    )

    # --- installments ---
    op.add_column("installments", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # --- payment_transactions ---
    op.add_column("payment_transactions", sa.Column("loan_id", sa.BigInteger(), nullable=True))
    op.create_index("idx_ptxn_loan_id", "payment_transactions", ["loan_id"])
    op.add_column("payment_transactions", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column("payment_transactions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payment_transactions", sa.Column("transaction_type", sa.String(30), nullable=True))
    op.add_column("payment_transactions", sa.Column("provider", sa.String(30), nullable=True))
    op.alter_column("payment_transactions", "installment_id", nullable=True)
    op.drop_constraint("chk_ptxn_status", "payment_transactions", type_="check")
    op.create_check_constraint(
        "chk_ptxn_status", "payment_transactions",
        "status IN ('initiated', 'pending', 'success', 'confirmed', 'failed', 'refunded', 'partially_refunded', 'chargeback')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_ptxn_status", "payment_transactions", type_="check")
    op.create_check_constraint(
        "chk_ptxn_status", "payment_transactions",
        "status IN ('initiated', 'pending', 'success', 'failed', 'refunded', 'partially_refunded', 'chargeback')",
    )
    op.alter_column("payment_transactions", "installment_id", nullable=False)
    op.drop_column("payment_transactions", "provider")
    op.drop_column("payment_transactions", "transaction_type")
    op.drop_column("payment_transactions", "deleted_at")
    op.drop_column("payment_transactions", "updated_at")
    op.drop_index("idx_ptxn_loan_id", table_name="payment_transactions")
    op.drop_column("payment_transactions", "loan_id")

    op.drop_column("installments", "deleted_at")

    op.drop_constraint("chk_loans_installment_count", "loans", type_="check")
    op.create_check_constraint(
        "chk_loans_installment_count", "loans",
        "installment_count >= 1 AND installment_count <= 6",
    )
    op.drop_constraint("chk_loans_plan_type", "loans", type_="check")
    op.create_check_constraint(
        "chk_loans_plan_type", "loans",
        "plan_type IN ('pay_in_3', 'pay_in_4', 'pay_in_6', 'pay_full')",
    )
    op.alter_column("loans", "expected_end_date", nullable=False)
    op.alter_column("loans", "start_date", nullable=False)
    op.drop_column("loans", "deleted_at")
