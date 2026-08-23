"""Add updated_at to purchase_executions

Revision ID: 084
Revises: 083
Create Date: 2026-08-22 00:00:00.000000

Same class of drift as 059/083: PurchaseExecution (packages/shared-python/
sk_shared/models/checkout.py) gets created_at/updated_at from TimestampMixin,
but the physical table was only ever given created_at (also its partition
key). Broke product-service's checkout-agent job queueing the moment a real
vcn.issued event reached it (UndefinedColumnError on every SELECT).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '084'
down_revision: Union[str, None] = '083'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "purchase_executions",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_column("purchase_executions", "updated_at")
