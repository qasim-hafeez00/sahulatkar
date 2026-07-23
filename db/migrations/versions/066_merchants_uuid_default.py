"""Add missing server_default to merchants.uuid

Revision ID: 066
Revises: 065
Create Date: 2026-07-04 00:00:00.000000

Every other UUID-mixin table in this codebase defaults uuid to
gen_random_uuid(); merchants was missing it, so any INSERT that didn't
explicitly supply a uuid (including this session's onboarding-approval
flow) hit a NOT NULL violation. Backfilling the default here so future
insert paths don't have to remember to set it manually.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '066'
down_revision: Union[str, None] = '065'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE merchants ALTER COLUMN uuid SET DEFAULT gen_random_uuid()")


def downgrade() -> None:
    op.execute("ALTER TABLE merchants ALTER COLUMN uuid DROP DEFAULT")
