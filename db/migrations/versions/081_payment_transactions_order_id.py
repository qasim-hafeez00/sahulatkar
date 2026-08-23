"""Add payment_transactions.order_id

Revision ID: 081
Revises: 080
Create Date: 2026-07-31 00:00:00.000001

Same class of bug as 078/079/080: `sk_shared.models.payment.PaymentTransaction`
declares `order_id: Mapped[Optional[int]]` (FK to orders.id), but the live
`payment_transactions` table has no such column at all — it only has an unrelated
`gateway_order_id` (a string, the payment gateway's own reference, not an FK to our
orders table). `POST /payments/down-payment` 500s on its lookup query before this fix.

No FK constraint here (unlike 079/080): `orders` is itself a partitioned table with a
composite primary key `(id, created_at)`, so Postgres has no plain unique constraint on
`id` alone to reference — the same reason no other table's FK into `orders` is enforced
at the DB level in this schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '081'
down_revision: Union[str, None] = '080'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payment_transactions', sa.Column('order_id', sa.BigInteger(), nullable=True))
    op.create_index('ix_payment_transactions_order_id', 'payment_transactions', ['order_id'])


def downgrade() -> None:
    op.drop_index('ix_payment_transactions_order_id', table_name='payment_transactions')
    op.drop_column('payment_transactions', 'order_id')
