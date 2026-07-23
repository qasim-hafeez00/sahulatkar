"""Add carts/cart_items tables and orders.loan_id for unified-financing carts

Revision ID: 051
Revises: 050
Create Date: 2026-07-03 00:00:00.000000

Introduces the "Universal Cart" feature: a Cart groups multiple product-url
Orders together. Each cart item still goes through the existing single-order
extraction/offer/accept pipeline unchanged; at Murabaha-signing time, orders
that share a cart are consolidated into ONE shared Loan (unified financing —
one combined down payment and repayment schedule), while each product still
gets its own per-item Wakalah/Murabaha contract (a Murabaha sale must name a
specific underlying asset). The new orders.loan_id column lets any sibling
order resolve the shared loan without changing the existing loans.order_id
(kept as the "primary" order for backward compatibility).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '051'
down_revision: Union[str, None] = '050'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "carts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("installment_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_carts_user_id_status", "carts", ["user_id", "status"])

    # NOTE: orders is a partitioned table (RANGE on created_at) with a composite
    # primary key (id, created_at), so it has no plain unique constraint on `id`
    # alone that Postgres will let a foreign key target. Every other table in this
    # schema that references an order (loans, wakalah_agreements, virtual_cards,
    # payment_transactions, ...) has the same limitation and stores order_id as a
    # plain application-level reference rather than a DB-enforced FK; cart_items
    # follows the same established convention here.
    op.create_table(
        "cart_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cart_id", sa.BigInteger(), sa.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cart_items_cart_id", "cart_items", ["cart_id"])

    op.add_column("orders", sa.Column("loan_id", sa.BigInteger(), sa.ForeignKey("loans.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_orders_loan_id", "orders", ["loan_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_loan_id", table_name="orders")
    op.drop_column("orders", "loan_id")
    op.drop_index("ix_cart_items_cart_id", table_name="cart_items")
    op.drop_table("cart_items")
    op.drop_index("ix_carts_user_id_status", table_name="carts")
    op.drop_table("carts")
