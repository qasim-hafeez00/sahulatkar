"""Drop non-partial installments(due_date, user_id) index; real partial index already exists

Revision ID: 086
Revises: 085
Create Date: 2026-08-28 00:00:00.000000

Migration 006 created `ix_installments_due_date_user_id_pending` as a plain
composite index on `installments(due_date, user_id)` -- despite the
"_pending" suffix in its name, it carries no `WHERE status = 'pending'`
predicate, so it indexes every installment row regardless of status
(paid/overdue/waived included) and will bloat and degrade at scale exactly
like a normal full-table index, contrary to what its name implies to anyone
reading the schema.

Separately, migration 039 (`HIGH-DB03: Missing indexes on recreated
partitioned tables`) already added `idx_inst_billing`:

    CREATE INDEX IF NOT EXISTS idx_inst_billing
        ON installments (due_date, user_id)
        WHERE status = 'pending';

which is a genuine partial index over the *exact same columns* and is what
BillingSweepService.load_due_installments() (`WHERE status = 'pending' AND
due_date <= :due_date`) actually benefits from. So the fix here is not to
add a second, redundant partial index with the identical definition (that
would just be a different flavor of the same index-bloat problem this
finding is about) -- it's to drop the misleadingly-named non-partial
duplicate from migration 006, leaving `idx_inst_billing` as the single
correct partial index the billing sweep depends on.

sk_shared.models.payment.Installment's `__table_args__` Index declaration
for `ix_installments_due_date_user_id_pending` is removed in the same change
so the ORM model doesn't drift back out of sync with the migrated schema.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '086'
down_revision: Union[str, None] = '085'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_INDEX_NAME = "ix_installments_due_date_user_id_pending"


def upgrade() -> None:
    # Plain (locking) DROP INDEX, consistent with every other index DDL in
    # this migration chain (e.g. 039's CREATE INDEX IF NOT EXISTS) -- all of
    # which already run inside Alembic's transactional DDL, where CONCURRENTLY
    # is not usable anyway.
    op.execute(f"DROP INDEX IF EXISTS {_OLD_INDEX_NAME};")


def downgrade() -> None:
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {_OLD_INDEX_NAME}
        ON installments (due_date, user_id);
        """
    )
