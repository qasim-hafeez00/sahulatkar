"""Add stripe_cardholder_id to virtual_cards

Revision ID: 048
Revises: 047
Create Date: 2026-04-25 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '048'
down_revision = '047_ledger_hardening_remaining'
branch_labels = None
depends_on = None


def upgrade():
    # add stripe_cardholder_id to virtual_cards
    with op.batch_alter_table('virtual_cards', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stripe_cardholder_id', sa.String(length=64), nullable=True))

def downgrade():
    with op.batch_alter_table('virtual_cards', schema=None) as batch_op:
        batch_op.drop_column('stripe_cardholder_id')
