"""Init M08 checkout

Revision ID: 008_init_m08_checkout
Revises: 007_init_m03_products
Create Date: 2026-04-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_init_m08_checkout"
down_revision: Union[str, None] = "007_init_m03_products"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "purchase_executions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("vcn_id", sa.BigInteger(), nullable=True),
        sa.Column("attempt_number", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("proxy_used", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("step_reached", sa.String(length=64), nullable=True),
        sa.Column("failure_type", sa.String(length=32), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("screenshot_s3", sa.String(length=512), nullable=True),
        sa.Column("merchant_order_id", sa.String(length=255), nullable=True),
        sa.Column("merchant_order_url", sa.String(length=2048), nullable=True),
        sa.Column("receipt_screenshot_s3", sa.String(length=512), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vcn_id"], ["virtual_cards.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_purchase_executions_order_created", "purchase_executions", ["order_id", "created_at"], unique=False)
    op.create_index("ix_purchase_executions_status_created", "purchase_executions", ["status", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_purchase_executions_status_created", table_name="purchase_executions")
    op.drop_index("ix_purchase_executions_order_created", table_name="purchase_executions")
    op.drop_table("purchase_executions")