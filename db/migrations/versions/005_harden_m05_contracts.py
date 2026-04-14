"""Harden M05 Contracts

Revision ID: 005_harden_m05_contracts
Revises: 004_init_m05_contracts
Create Date: 2026-04-08 17:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005_harden_m05_contracts'
down_revision: Union[str, None] = '004_init_m05_contracts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Update orders
    op.add_column('orders', sa.Column('product_description', sa.Text(), nullable=True))

    # 2. Update wakalah_agreements
    op.add_column('wakalah_agreements', sa.Column('principal_name', sa.String(length=200), nullable=True))
    op.add_column('wakalah_agreements', sa.Column('principal_cnic', sa.String(length=20), nullable=True))
    op.add_column('wakalah_agreements', sa.Column('principal_phone', sa.String(length=20), nullable=True))
    op.add_column('wakalah_agreements', sa.Column('agent_name', sa.String(length=100), server_default='SahulatKar (Pvt) Ltd.', nullable=False))
    op.add_column('wakalah_agreements', sa.Column('agent_secp_license', sa.String(length=50), server_default='SECP-L-12345', nullable=False))
    op.add_column('wakalah_agreements', sa.Column('product_description', sa.Text(), nullable=True))
    op.add_column('wakalah_agreements', sa.Column('merchant_name', sa.String(length=255), nullable=True))
    op.add_column('wakalah_agreements', sa.Column('product_url', sa.String(length=2048), nullable=True))
    op.add_column('wakalah_agreements', sa.Column('price_variance_pct', sa.Numeric(precision=4, scale=2), server_default='5.00', nullable=False))
    op.add_column('wakalah_agreements', sa.Column('valid_until', sa.DateTime(), nullable=True))

    # 3. Update murabaha_contracts
    op.add_column('murabaha_contracts', sa.Column('currency', sa.String(length=3), server_default='PKR', nullable=False))
    op.add_column('murabaha_contracts', sa.Column('template_version', sa.String(length=10), server_default='1.0', nullable=False))
    op.add_column('murabaha_contracts', sa.Column('validated_by_shariah_board', sa.Boolean(), server_default=sa.text('false'), nullable=False))

def downgrade() -> None:
    # 3. Revert murabaha_contracts
    op.drop_column('murabaha_contracts', 'validated_by_shariah_board')
    op.drop_column('murabaha_contracts', 'template_version')
    op.drop_column('murabaha_contracts', 'currency')

    # 2. Revert wakalah_agreements
    op.drop_column('wakalah_agreements', 'valid_until')
    op.drop_column('wakalah_agreements', 'price_variance_pct')
    op.drop_column('wakalah_agreements', 'product_url')
    op.drop_column('wakalah_agreements', 'merchant_name')
    op.drop_column('wakalah_agreements', 'product_description')
    op.drop_column('wakalah_agreements', 'agent_secp_license')
    op.drop_column('wakalah_agreements', 'agent_name')
    op.drop_column('wakalah_agreements', 'principal_phone')
    op.drop_column('wakalah_agreements', 'principal_cnic')
    op.drop_column('wakalah_agreements', 'principal_name')

    # 1. Revert orders
    op.drop_column('orders', 'product_description')
