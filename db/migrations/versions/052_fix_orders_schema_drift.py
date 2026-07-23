"""Reconcile orders table with the current Order ORM model

Revision ID: 052
Revises: 051
Create Date: 2026-07-03 00:00:00.000000

The physical `orders` table was built from an older, richer schema (input_url,
product_snapshot, product_cost, platform_profit NOT NULL with no defaults, plus
several other columns) that predates the current, simpler sk_shared.models.order
Order model. None of the code that creates orders today (OrderService.initiate,
CartService) populates those columns, and the model's `deleted_at` (used for
every soft-delete check, e.g. order lookups, cancellation, active-order-count)
was never added to the table at all — so order creation and every downstream
order lookup has been failing outright. This is additive/relaxing only: no
columns are dropped, so anything else still reading the old columns is
unaffected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '052'
down_revision: Union[str, None] = '051'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("orders", "input_url", existing_type=sa.String(2048), nullable=True)
    op.alter_column("orders", "product_snapshot", existing_type=postgresql.JSONB(), nullable=True)
    op.alter_column("orders", "product_cost", existing_type=sa.Numeric(14, 2), nullable=True)
    op.alter_column("orders", "platform_profit", existing_type=sa.Numeric(14, 2), nullable=True)


def downgrade() -> None:
    op.alter_column("orders", "platform_profit", existing_type=sa.Numeric(14, 2), nullable=False)
    op.alter_column("orders", "product_cost", existing_type=sa.Numeric(14, 2), nullable=False)
    op.alter_column("orders", "product_snapshot", existing_type=postgresql.JSONB(), nullable=False)
    op.alter_column("orders", "input_url", existing_type=sa.String(2048), nullable=False)
    op.drop_column("orders", "deleted_at")
