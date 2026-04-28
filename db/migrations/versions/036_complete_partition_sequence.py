"""Complete Partition Sequence

Revision ID: 036_complete_partition_sequence
Revises: 035_align_compliance_admin_system
Create Date: 2026-04-15 05:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '036_complete_partition_sequence'
down_revision: Union[str, None] = '035_align_compliance_admin_system'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Purchase Executions (Quarterly)
    op.execute("CREATE TABLE IF NOT EXISTS pe_2025_q2 PARTITION OF purchase_executions FOR VALUES FROM ('2025-04-01') TO ('2025-07-01')")
    op.execute("CREATE TABLE IF NOT EXISTS pe_2025_q3 PARTITION OF purchase_executions FOR VALUES FROM ('2025-07-01') TO ('2025-10-01')")
    op.execute("CREATE TABLE IF NOT EXISTS pe_2025_q4 PARTITION OF purchase_executions FOR VALUES FROM ('2025-10-01') TO ('2026-01-01')")

    # 2. Payment Transactions (Quarterly)
    op.execute("CREATE TABLE IF NOT EXISTS ptxn_2025_q2 PARTITION OF payment_transactions FOR VALUES FROM ('2025-04-01') TO ('2025-07-01')")
    op.execute("CREATE TABLE IF NOT EXISTS ptxn_2025_q3 PARTITION OF payment_transactions FOR VALUES FROM ('2025-07-01') TO ('2025-10-01')")
    op.execute("CREATE TABLE IF NOT EXISTS ptxn_2025_q4 PARTITION OF payment_transactions FOR VALUES FROM ('2025-10-01') TO ('2026-01-01')")

    # 3. Tracking Events (Quarterly)
    op.execute("CREATE TABLE IF NOT EXISTS te_2025_q1 PARTITION OF tracking_events FOR VALUES FROM ('2025-01-01') TO ('2025-04-01')")
    op.execute("CREATE TABLE IF NOT EXISTS te_2025_q2 PARTITION OF tracking_events FOR VALUES FROM ('2025-04-01') TO ('2025-07-01')")
    op.execute("CREATE TABLE IF NOT EXISTS te_2025_q3 PARTITION OF tracking_events FOR VALUES FROM ('2025-07-01') TO ('2025-10-01')")
    op.execute("CREATE TABLE IF NOT EXISTS te_2025_q4 PARTITION OF tracking_events FOR VALUES FROM ('2025-10-01') TO ('2026-01-01')")

    # 4. Notifications Queue (Quarterly)
    op.execute("CREATE TABLE IF NOT EXISTS nq_2025_q2 PARTITION OF notifications_queue FOR VALUES FROM ('2025-04-01') TO ('2025-07-01')")
    op.execute("CREATE TABLE IF NOT EXISTS nq_2025_q3 PARTITION OF notifications_queue FOR VALUES FROM ('2025-07-01') TO ('2025-10-01')")
    op.execute("CREATE TABLE IF NOT EXISTS nq_2025_q4 PARTITION OF notifications_queue FOR VALUES FROM ('2025-10-01') TO ('2026-01-01')")

    # 5. Audit Trails (Monthly)
    months = ['02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
    dates = [
        ('2025-02-01', '2025-03-01'), ('2025-03-01', '2025-04-01'),
        ('2025-04-01', '2025-05-01'), ('2025-05-01', '2025-06-01'),
        ('2025-06-01', '2025-07-01'), ('2025-07-01', '2025-08-01'),
        ('2025-08-01', '2025-09-01'), ('2025-09-01', '2025-10-01'),
        ('2025-10-01', '2025-11-01'), ('2025-11-01', '2025-12-01'),
        ('2025-12-01', '2026-01-01')
    ]
    for i, (start, end) in enumerate(dates):
        month = months[i]
        op.execute(f"CREATE TABLE IF NOT EXISTS audit_trails_2025_m{month} PARTITION OF audit_trails FOR VALUES FROM ('{start}') TO ('{end}')")


def downgrade() -> None:
    # Drop the additional partition child tables created in upgrade().
    # The parent partitioned tables are owned by earlier migrations and not dropped here.
    months = ['02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
    for month in months:
        op.execute(f"DROP TABLE IF EXISTS audit_trails_2025_m{month}")
    for q in ['q2', 'q3', 'q4']:
        op.execute(f"DROP TABLE IF EXISTS nq_2025_{q}")
    for q in ['q1', 'q2', 'q3', 'q4']:
        op.execute(f"DROP TABLE IF EXISTS te_2025_{q}")
    for q in ['q2', 'q3', 'q4']:
        op.execute(f"DROP TABLE IF EXISTS ptxn_2025_{q}")
    for q in ['q2', 'q3', 'q4']:
        op.execute(f"DROP TABLE IF EXISTS pe_2025_{q}")
