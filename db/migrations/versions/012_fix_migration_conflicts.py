"""Fix Migration Conflicts

Revision ID: 012_fix_migration_conflicts
Revises: 011_init_m11_ledger
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '012_fix_migration_conflicts'
down_revision: Union[str, None] = '011_init_m11_ledger'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Tables were moved to 004 to satisfy 006 dependencies
    pass

def downgrade() -> None:
    pass
