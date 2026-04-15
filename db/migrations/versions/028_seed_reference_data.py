"""Seed Reference Data Final

Revision ID: 028_seed_reference_data
Revises: 027_missing_domain_tables
Create Date: 2026-04-15 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '028_seed_reference_data'
down_revision: Union[str, None] = '027_missing_domain_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Seed Prohibited Categories
    prohibited_cats_table = table('prohibited_categories',
        column('category_name', sa.String),
        column('keywords', sa.ARRAY(sa.Text)),
        column('shariah_basis', sa.Text)
    )
    op.bulk_insert(prohibited_cats_table, [
        {'category_name': 'Alcohol & Spirits', 'keywords': ['alcohol', 'liquor', 'wine', 'beer', 'vodka', 'whiskey'], 'shariah_basis': 'Strictly prohibited in Islamic Law (Khamr).'},
        {'category_name': 'Gambling & Betting', 'keywords': ['gambling', 'betting', 'casino', 'lottery', 'poker', 'slots'], 'shariah_basis': 'Prohibited as Maisir (Game of Chance).'},
        {'category_name': 'Pork Products', 'keywords': ['pork', 'pig', 'bacon', 'ham', 'lard'], 'shariah_basis': 'Forbidden dietary item (Haram).'},
        {'category_name': 'Adult Content/Services', 'keywords': ['adult', 'porn', 'sex toy', 'lingerie', 'dating'], 'shariah_basis': 'Prohibited to facilitate immorality.'},
        {'category_name': 'Tobacco & E-Cigarettes', 'keywords': ['tobacco', 'cigarette', 'cigar', 'vape', 'pod', 'e-cig'], 'shariah_basis': 'Harmful to health (Tahrim due to harm).'},
        {'category_name': 'Interest-based Financials', 'keywords': ['interest', 'forex', 'crypto', 'bond'], 'shariah_basis': 'Prohibited due to Riba (Usury/Interest).'},
    ])

    # 2. Seed System Settings
    system_settings_table = table('system_settings',
        column('key', sa.String),
        column('value', postgresql.JSONB),
        column('description', sa.Text)
    )
    op.bulk_insert(system_settings_table, [
        {'key': 'min_credit_limit', 'value': 5000, 'description': 'Minimum credit limit assigned to new users.'},
        {'key': 'max_credit_limit', 'value': 100000, 'description': 'Maximum credit limit for standard retail users.'},
        {'key': 'default_profit_rate', 'value': 4.5, 'description': 'Default Murabaha profit rate percentage (e.g. 4.5%).'},
        {'key': 'late_fee_per_day', 'value': 50, 'description': 'Late fee amount (PKR) added per day of default (routed to charity).'},
        {'key': 'tax_rate_pct', 'value': 17.0, 'description': 'Standard sales tax rate in Pakistan.'},
        {'key': 'platform_fee_fixed', 'value': 99, 'description': 'Fixed platform processing fee per order.'},
    ])


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE key IN ('min_credit_limit', 'max_credit_limit', 'default_profit_rate', 'late_fee_per_day', 'tax_rate_pct', 'platform_fee_fixed')")
    op.execute("DELETE FROM prohibited_categories")
