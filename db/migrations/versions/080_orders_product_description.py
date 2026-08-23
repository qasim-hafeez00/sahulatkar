"""Add orders.product_description

Revision ID: 080
Revises: 079
Create Date: 2026-07-30 00:00:00.000004

Same class of bug as 078/079: `sk_shared.models.order.Order` declares
`product_description: Mapped[Optional[str]]`, but the live `orders` table only has
unrelated `input_url`/`canonical_url` columns instead — nothing in apps/ or packages/
reads or writes `input_url`/`canonical_url` (grepped, zero hits), so they're left alone
and this adds the column the model actually needs. Every `POST /cart/items` call was
500ing on `INSERT INTO orders (...)` before this fix, since OrderService.initiate()
always writes product_description.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '080'
down_revision: Union[str, None] = '079'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('product_description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'product_description')
