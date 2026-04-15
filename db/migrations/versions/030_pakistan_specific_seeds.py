"""Pakistan Specific Seeds

Revision ID: 030_pakistan_specific_seeds
Revises: 029_advanced_db_objects
Create Date: 2026-04-15 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column

# revision identifiers, used by Alembic.
revision: str = '030_pakistan_specific_seeds'
down_revision: Union[str, None] = '029_advanced_db_objects'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Pakistan Cities
    # op.create_table was missed for pakistan_cities in 027 (Wait, let me check 027).
    # Ah, I missed many "Pakistan Specific" tables. I'll create them here.
    
    op.create_table(
        "pakistan_cities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_urdu", sa.String(length=100), nullable=True),
        sa.Column("province", sa.String(length=50), nullable=False),
        sa.Column("is_metro", sa.Boolean(), server_default='false', nullable=False),
        sa.Column("population", sa.Integer(), nullable=True),
        sa.Column("has_courier_hub", sa.Boolean(), server_default='false', nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name")
    )

    op.create_table(
        "pakistan_postal_codes",
        sa.Column("postal_code", sa.String(length=10), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("province", sa.String(length=50), nullable=False),
        sa.Column("is_serviceable", sa.Boolean(), server_default='false', nullable=False),
        sa.PrimaryKeyConstraint("postal_code")
    )

    op.create_table(
        "islamic_calendar",
        sa.Column("gregorian_date", sa.Date(), nullable=False),
        sa.Column("hijri_year", sa.SmallInteger(), nullable=False),
        sa.Column("hijri_month", sa.SmallInteger(), nullable=False),
        sa.Column("hijri_day", sa.SmallInteger(), nullable=False),
        sa.Column("month_name_en", sa.String(length=20), nullable=True),
        sa.Column("is_ramadan", sa.Boolean(), server_default='false', nullable=False),
        sa.Column("is_eid_ul_fitr", sa.Boolean(), server_default='false', nullable=False),
        sa.Column("is_eid_ul_adha", sa.Boolean(), server_default='false', nullable=False),
        sa.Column("is_public_holiday", sa.Boolean(), server_default='false', nullable=False),
        sa.PrimaryKeyConstraint("gregorian_date")
    )

    # 2. Seed Cities
    cities_table = table('pakistan_cities',
        column('name', sa.String),
        column('name_urdu', sa.String),
        column('province', sa.String),
        column('is_metro', sa.Boolean)
    )
    op.bulk_insert(cities_table, [
        {'name': 'Karachi', 'name_urdu': 'کراچی', 'province': 'Sindh', 'is_metro': True},
        {'name': 'Lahore', 'name_urdu': 'لاہور', 'province': 'Punjab', 'is_metro': True},
        {'name': 'Islamabad', 'name_urdu': 'اسلام آباد', 'province': 'ICT', 'is_metro': True},
        {'name': 'Faisalabad', 'name_urdu': 'فیصل آباد', 'province': 'Punjab', 'is_metro': True},
        {'name': 'Rawalpindi', 'name_urdu': 'راولپنڈی', 'province': 'Punjab', 'is_metro': True},
    ])

    # 3. Seed Sample Calendar (Ramadan 2025 Start)
    calendar_table = table('islamic_calendar',
        column('gregorian_date', sa.Date),
        column('hijri_year', sa.SmallInteger),
        column('hijri_month', sa.SmallInteger),
        column('hijri_day', sa.SmallInteger),
        column('month_name_en', sa.String),
        column('is_ramadan', sa.Boolean)
    )
    from datetime import date
    op.bulk_insert(calendar_table, [
        {'gregorian_date': date(2025, 3, 1), 'hijri_year': 1446, 'hijri_month': 9, 'hijri_day': 1, 'month_name_en': 'Ramadan', 'is_ramadan': True},
        {'gregorian_date': date(2025, 3, 2), 'hijri_year': 1446, 'hijri_month': 9, 'hijri_day': 2, 'month_name_en': 'Ramadan', 'is_ramadan': True},
        # ... simplified for brevity in this migration, application should populate full range
    ])


def downgrade() -> None:
    op.drop_table("islamic_calendar")
    op.drop_table("pakistan_postal_codes")
    op.drop_table("pakistan_cities")
