"""Add Murabaha loan origination GL accounts

Revision ID: 050
Revises: 049a
Create Date: 2026-04-28 00:00:00.000000

These three accounts support the loan.created journal entry that posts the
initial Murabaha financing recognition when a contract is signed (DB-GAP + CROSS-12).
"""
from typing import Sequence, Union

from alembic import op

revision: str = '050'
down_revision: Union[str, None] = '049a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO ledger_accounts (account_code, account_name, account_type, normal_balance, is_active, notes)
        VALUES
          ('1101', 'Murabaha Financing Receivable', 'asset',     'debit',  true,
           'Initial receivable recognised at Murabaha contract signing (before VCN charge)'),
          ('2101', 'Loan Loss Reserve',              'liability', 'credit', true,
           'Reserve for expected credit losses on Murabaha portfolio'),
          ('2201', 'Murabaha Cost Payable',          'liability', 'credit', true,
           'Obligation to pay merchant the cost price of goods procured for customer'),
          ('2202', 'Deferred Murabaha Profit',       'liability', 'credit', true,
           'Unearned profit on Murabaha financing, recognised over loan life')
        ON CONFLICT (account_code) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM ledger_accounts
        WHERE account_code IN ('1101', '2201', '2202')
    """)
