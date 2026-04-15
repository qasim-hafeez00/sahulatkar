"""Advanced DB Objects

Revision ID: 029_advanced_db_objects
Revises: 028_seed_reference_data
Create Date: 2026-04-15 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '029_advanced_db_objects'
down_revision: Union[str, None] = '028_seed_reference_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Apply Audit Triggers to 30 Sensitive Tables
    sensitive_tables = [
        'users', 'loans', 'installments', 'payment_transactions',
        'murabaha_contracts', 'wakalah_agreements', 'virtual_cards',
        'credit_applications', 'credit_limit_history', 'risk_assessments',
        'fraud_alerts', 'user_kyc_verifications', 'user_payment_methods',
        'user_bank_accounts', 'orders', 'chargebacks', 'refunds',
        'late_fee_charity_allocations', 'journal_entries', 'settlements',
        'admin_users', 'roles', 'permissions', 'role_permissions',
        'system_settings', 'feature_flags', 'api_keys',
        'promotional_codes', 'user_consent_records', 'data_deletion_requests'
    ]

    for table_name in sensitive_tables:
        trigger_name = f"trg_{table_name}_audit"
        # Using a conditional create to avoid conflicts
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = '{trigger_name}') THEN
                    CREATE TRIGGER {trigger_name}
                    AFTER INSERT OR UPDATE OR DELETE ON {table_name}
                    FOR EACH ROW EXECUTE FUNCTION fn_log_audit();
                END IF;
            END $$;
        """)

    # 2. Materialized Views for Reporting
    # 2.1 Daily revenue summary
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_revenue AS
        SELECT
            DATE(o.created_at AT TIME ZONE 'Asia/Karachi') AS report_date,
            COUNT(DISTINCT o.id)               AS orders_completed,
            SUM(o.total_amount)                AS gmv,
            SUM(l.profit_amount)               AS gross_profit,
            AVG(o.total_amount)                AS avg_order_value,
            COUNT(DISTINCT o.user_id)          AS unique_buyers
        FROM orders o
        JOIN loans l ON l.order_id = o.id
        WHERE o.status = 'completed'
        GROUP BY DATE(o.created_at AT TIME ZONE 'Asia/Karachi');
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_revenue_date ON mv_daily_revenue(report_date)")

    # 2.2 Portfolio health
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_loan_portfolio AS
        SELECT
            l.status,
            COUNT(*)                           AS loan_count,
            SUM(l.total_outstanding)           AS total_outstanding,
            SUM(l.late_fee_total)              AS total_late_fees,
            AVG(l.total_outstanding)           AS avg_outstanding,
            COUNT(*) FILTER (WHERE l.status='defaulted') AS defaults
        FROM loans l
        GROUP BY l.status;
    """)

    # 2.3 Merchant performance
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_merchant_performance AS
        SELECT
            m.id, m.name, m.domain,
            COUNT(o.id)                        AS total_orders,
            AVG(CASE WHEN o.status='completed' THEN 1 ELSE 0 END) AS success_rate,
            SUM(o.total_amount)                AS total_gmv
        FROM merchants m
        LEFT JOIN orders o ON o.merchant_id = m.id
        GROUP BY m.id, m.name, m.domain;
    """)


def downgrade() -> None:
    # Drop Materialized Views
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_merchant_performance")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_loan_portfolio")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_daily_revenue")

    # Drop Audit Triggers
    sensitive_tables = [
        'users', 'loans', 'installments', 'payment_transactions',
        'murabaha_contracts', 'wakalah_agreements', 'virtual_cards',
        'credit_applications', 'credit_limit_history', 'risk_assessments',
        'fraud_alerts', 'user_kyc_verifications', 'user_payment_methods',
        'user_bank_accounts', 'orders', 'chargebacks', 'refunds',
        'late_fee_charity_allocations', 'journal_entries', 'settlements',
        'admin_users', 'roles', 'permissions', 'role_permissions',
        'system_settings', 'feature_flags', 'api_keys',
        'promotional_codes', 'user_consent_records', 'data_deletion_requests'
    ]
    for table_name in sensitive_tables:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_audit ON {table_name}")
