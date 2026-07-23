"""Add order_status_history table expected by the Order ORM model

Revision ID: 053
Revises: 052
Create Date: 2026-07-03 00:00:01.000000

Continuation of the orders schema-drift fix started in 052: the physical
database has an `order_state_history` table from an older/richer order schema,
but sk_shared.models.order.OrderStatusHistory (used throughout OrderService,
ContractSignerService, cart_service, etc.) expects a table literally named
`order_status_history` with a much simpler shape. That table never existed,
so every order status transition write has been failing.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '053'
down_revision: Union[str, None] = '052'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("from_status", sa.String(50), nullable=True),
        sa.Column("to_status", sa.String(50), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_order_status_history_order_id", "order_status_history", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_status_history_order_id", table_name="order_status_history")
    op.drop_table("order_status_history")
