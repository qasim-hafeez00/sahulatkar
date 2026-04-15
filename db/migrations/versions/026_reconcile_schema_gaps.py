"""Reconcile schema gaps

Revision ID: 026_reconcile_schema_gaps
Revises: 025_system_integration
Create Date: 2026-04-15 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '026_reconcile_schema_gaps'
down_revision: Union[str, None] = '025_system_integration'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users Table Enhancements (adding only what's truly missing after 023)
    op.add_column('users', sa.Column('full_name', sa.String(length=200), nullable=True))
    op.add_column('users', sa.Column('is_blocked', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('recovery_risk_score', sa.Numeric(5, 2), nullable=True))
    op.add_column('users', sa.Column('cnic_expiry_date', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('is_suspended', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('suspension_reason', sa.Text(), nullable=True))
    
    # 1b. Orders Table Enhancements
    op.add_column('orders', sa.Column('merchant_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_orders_merchant_id', 'orders', 'merchants', ['merchant_id'], ['id'], ondelete='SET NULL')

    # 2. Loans Table Enhancements
    op.add_column('loans', sa.Column('is_rescheduled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('loans', sa.Column('rescheduled_from_loan_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_loans_rescheduled_from', 'loans', 'loans', ['rescheduled_from_loan_id'], ['id'])

    # 3. Installments Table Enhancements
    op.add_column('installments', sa.Column('late_fee_waiver_by', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_installments_waiver_by', 'installments', 'admin_users', ['late_fee_waiver_by'], ['id'])

    # 4. Shipments Table Enhancements
    op.add_column('shipments', sa.Column('is_fragile', sa.Boolean(), server_default='false', nullable=False))

    # 5. Virtual Cards Table Enhancements
    op.add_column('virtual_cards', sa.Column('billing_zip', sa.String(length=10), nullable=True))


def downgrade() -> None:
    # Shipments
    op.drop_column('shipments', 'is_fragile')

    # Installments
    op.drop_constraint('fk_installments_waiver_by', 'installments', type_='foreignkey')
    op.drop_column('installments', 'late_fee_waiver_by')

    # Loans
    op.drop_constraint('fk_loans_rescheduled_from', 'loans', type_='foreignkey')
    op.drop_column('loans', 'rescheduled_from_loan_id')
    op.drop_column('loans', 'is_rescheduled')

    # Orders
    op.drop_constraint('fk_orders_merchant_id', 'orders', type_='foreignkey')
    op.drop_column('orders', 'merchant_id')

    # Users
    op.drop_column('users', 'suspension_reason')
    op.drop_column('users', 'is_suspended')
    op.drop_column('users', 'cnic_expiry_date')
    op.drop_column('users', 'recovery_risk_score')
    op.drop_column('users', 'is_blocked')
    op.drop_column('users', 'full_name')

    # Virtual Cards
    op.drop_column('virtual_cards', 'billing_zip')
