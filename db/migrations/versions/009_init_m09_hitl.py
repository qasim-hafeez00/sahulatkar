"""Init M09 hitl

Revision ID: 009_init_m09_hitl
Revises: 008_init_m08_checkout
Create Date: 2026-04-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_init_m09_hitl"
down_revision: Union[str, None] = "008_init_m08_checkout"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hitl_queue",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("execution_id", sa.BigInteger(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("assigned_to", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("screenshot_s3", sa.String(length=512), nullable=True),
        sa.Column("resolution", sa.String(length=100), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("in_progress_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("sla_deadline", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["purchase_executions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_hitl_queue_status_priority", "hitl_queue", ["status", "priority"], unique=False)
    op.create_index("ix_hitl_queue_assigned_status", "hitl_queue", ["assigned_to", "status"], unique=False)
    op.create_index("ix_hitl_queue_sla_deadline", "hitl_queue", ["sla_deadline"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_hitl_queue_sla_deadline", table_name="hitl_queue")
    op.drop_index("ix_hitl_queue_assigned_status", table_name="hitl_queue")
    op.drop_index("ix_hitl_queue_status_priority", table_name="hitl_queue")
    op.drop_table("hitl_queue")