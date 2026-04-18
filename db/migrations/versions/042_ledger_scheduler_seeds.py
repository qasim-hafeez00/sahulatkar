"""Ledger Scheduler Seeds

Revision ID: 042_ledger_scheduler_seeds
Revises: 041_production_hardening
Create Date: 2026-04-16 12:30:00.000000

Seeds the scheduled_tasks table with ledger-service cron jobs that are
explicitly defined in the service configuration.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "042_ledger_scheduler_seeds"
down_revision: Union[str, None] = "041_production_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO scheduled_tasks (task_name, schedule_cron, is_active) VALUES
            ('ledger_billing_sweep', '0 8 * * *', true),
            ('ledger_reconciliation', '0 2 * * *', true)
        ON CONFLICT (task_name) DO UPDATE
            SET schedule_cron = EXCLUDED.schedule_cron,
                is_active = EXCLUDED.is_active,
                updated_at = now();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM scheduled_tasks
        WHERE task_name IN ('ledger_billing_sweep', 'ledger_reconciliation');
        """
    )
