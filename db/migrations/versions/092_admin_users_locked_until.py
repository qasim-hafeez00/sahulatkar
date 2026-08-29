"""Add missing admin_users.locked_until column

Revision ID: 092
Revises: 091
Create Date: 2026-08-28 00:00:00.000000

CRITICAL bug found while building tests/e2e/test_admin_workflows.py:
AdminUser.locked_until (packages/shared-python/sk_shared/models/auth.py) is
declared on the ORM model and is unconditionally SELECTed by
AuthService.admin_login on EVERY admin login attempt (src/services/auth.py),
but the column was never actually migrated onto the real admin_users table --
live-verified against a real Postgres instance with all prior migrations
applied (\\d admin_users has no locked_until column). The result: every real
admin login, in any environment running against real Postgres, crashes with
a 500 (asyncpg.exceptions.UndefinedColumnError) before ever reaching the
password/MFA checks. This was invisible to the existing gateway unit test
suite because it runs against SQLite with tables created from the current
ORM metadata directly, not through Alembic -- the same class of ORM/schema
drift already documented for Ledger Service's tables (migrations 089-091),
here hitting the single most-used admin entrypoint instead.

The sibling column `users.locked_until` (customer login lockout) already
exists on the real schema and is unaffected -- this drift is scoped to
admin_users specifically.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '092'
down_revision: Union[str, None] = '091'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("locked_until", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admin_users", "locked_until")
