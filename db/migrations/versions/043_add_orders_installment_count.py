"""Add installment count to orders

Revision ID: 043_add_orders_installment_count
Revises: 042_ledger_scheduler_seeds
Create Date: 2026-04-19 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "043_add_orders_installment_count"
down_revision: Union[str, None] = "042_ledger_scheduler_seeds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("installment_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "installment_count")
