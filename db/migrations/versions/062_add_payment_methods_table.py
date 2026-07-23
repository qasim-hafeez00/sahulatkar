"""Add payment_methods table

Revision ID: 062
Revises: 061
Create Date: 2026-07-03 00:00:10.000000

Migration 006 (init_m06_payments) claims to create payment_methods, but the
live database never actually had it -- same class of schema drift discovered
throughout this codebase (the physical payment_transactions table itself is a
richer, older schema than 006 describes, with no FK to payment_methods at
all). This adds the table the PaymentMethod ORM model expects, without a FK
from the partitioned payment_transactions table (consistent with this
codebase's existing convention of not adding FKs to/from partitioned tables).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '062'
down_revision: Union[str, None] = '061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_methods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("method_type", sa.String(length=20), nullable=False),
        sa.Column("tokenized_reference", sa.String(length=255), nullable=False),
        sa.Column("masked_pan", sa.String(length=19), nullable=True),
        sa.Column("expiry_month", sa.String(length=2), nullable=True),
        sa.Column("expiry_year", sa.String(length=4), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_payment_methods_user_id", "payment_methods", ["user_id"], unique=False)
    op.create_index("ix_payment_methods_provider_reference", "payment_methods", ["provider", "tokenized_reference"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payment_methods_provider_reference", table_name="payment_methods")
    op.drop_index("ix_payment_methods_user_id", table_name="payment_methods")
    op.drop_table("payment_methods")
