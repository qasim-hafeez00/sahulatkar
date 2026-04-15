"""Compliance Audit

Revision ID: 024_compliance_audit
Revises: 023_admin_team_remaining
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '024_compliance_audit'
down_revision: Union[str, None] = '023_admin_team_remaining'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # --- 1. Tables ---
    op.create_table(
        "audit_trails",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("table_name", sa.String(length=100), nullable=False),
        sa.Column("record_id", sa.BigInteger(), nullable=False),
        sa.Column("operation", sa.String(length=10), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("old_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("changed_fields", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("operation IN ('INSERT','UPDATE','DELETE')"),
        sa.CheckConstraint("actor_type IN ('customer','admin','system','api')"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_trails_table_record", "audit_trails", ["table_name", "record_id"], unique=False)
    op.create_index("ix_audit_trails_actor", "audit_trails", ["actor_type", "actor_id"], unique=False)
    op.create_index("ix_audit_trails_changed_at", "audit_trails", [sa.text("changed_at DESC")], unique=False)

    op.create_table(
        "regulatory_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("pdf_s3", sa.String(length=512), nullable=True),
        sa.Column("reference_number", sa.String(length=100), nullable=True),
        sa.Column("generated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("report_type IN ('monthly_bnpl','annual_kyc','aml_sar','secp_return','sbp_rcd1','fbr_gst3')"),
        sa.ForeignKeyConstraint(["generated_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )

    op.create_table(
        "data_deletion_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("request_type", sa.String(length=30), nullable=False),
        sa.Column("verification_method", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column("tables_cleared", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("request_type IN ('erasure','portability','correction')"),
        sa.CheckConstraint("status IN ('pending','verified','in_progress','completed','rejected')"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )

    op.create_table(
        "consent_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("consent_type", sa.String(length=50), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("consented_at", sa.DateTime(), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.CheckConstraint("decision IN ('accepted','withdrawn')"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consent_logs_user_id_type_consented_at", "consent_logs", ["user_id", "consent_type", sa.text("consented_at DESC")], unique=False)

    op.create_table(
        "aml_suspicious_activity_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("alert_id", sa.BigInteger(), nullable=True),
        sa.Column("transaction_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("suspicion_basis", sa.Text(), nullable=False),
        sa.Column("filed_with", sa.String(length=30), nullable=False, server_default='FMU'),
        sa.Column("filed_at", sa.DateTime(), nullable=True),
        sa.Column("reference_number", sa.String(length=100), nullable=True),
        sa.Column("filed_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["fraud_alerts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["filed_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_aml_sar_user_id_created_at", "aml_suspicious_activity_reports", ["user_id", sa.text("created_at DESC")], unique=False)


    # --- 2. Triggers and Utility Functions ---
    op.execute("""
CREATE OR REPLACE FUNCTION fn_log_audit()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE v_old JSONB; v_new JSONB; v_changed TEXT[];
BEGIN
    IF TG_OP='DELETE' THEN v_old:=to_jsonb(OLD); v_new:=NULL;
    ELSIF TG_OP='INSERT' THEN v_old:=NULL; v_new:=to_jsonb(NEW);
    ELSE v_old:=to_jsonb(OLD); v_new:=to_jsonb(NEW);
        SELECT array_agg(key) INTO v_changed FROM jsonb_each(v_old)
        WHERE (v_old->key)::text IS DISTINCT FROM (v_new->key)::text;
    END IF;
    INSERT INTO audit_trails(table_name,record_id,operation,actor_type,actor_id,
        ip_address,request_id,old_values,new_values,changed_fields)
    VALUES(TG_TABLE_NAME,
        COALESCE((v_new->>'id')::BIGINT,(v_old->>'id')::BIGINT),
        TG_OP,
        NULLIF(current_setting('app.actor_type',TRUE),''),
        NULLIF(current_setting('app.actor_id',TRUE),'')::BIGINT,
        NULLIF(current_setting('app.ip_address',TRUE),'')::INET,
        NULLIF(current_setting('app.request_id',TRUE),'')::UUID,
        v_old,v_new,v_changed);
    RETURN COALESCE(NEW,OLD);
END; $$;
    """)

    op.execute("CREATE SEQUENCE IF NOT EXISTS seq_order_number START 1000 INCREMENT 1;")
    op.execute("""
CREATE OR REPLACE FUNCTION fn_generate_order_number()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.order_number IS NULL THEN
        NEW.order_number := 'SAK-' || TO_CHAR(NOW(),'YYYY') || '-' || 
                            LPAD(nextval('seq_order_number')::TEXT, 7, '0');
    END IF;
    RETURN NEW;
END; $$;
    """)

    op.execute("""
CREATE OR REPLACE FUNCTION fn_recalculate_available_credit()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_outstanding DECIMAL(14,2);
BEGIN
    SELECT COALESCE(SUM(total_outstanding), 0) INTO v_outstanding
    FROM loans WHERE user_id = COALESCE(NEW.user_id, OLD.user_id)
    AND status IN ('active','partially_paid');
    UPDATE users SET total_outstanding = v_outstanding,
        available_credit = GREATEST(credit_limit - v_outstanding, 0)
    WHERE id = COALESCE(NEW.user_id, OLD.user_id);
    RETURN COALESCE(NEW, OLD);
END; $$;
    """)

    op.execute("""
CREATE OR REPLACE FUNCTION fn_apply_late_fee()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_days_overdue INTEGER; v_late_fee DECIMAL(14,2);
BEGIN
    IF OLD.status != 'overdue' AND NEW.status = 'overdue' THEN
        v_days_overdue := CURRENT_DATE - NEW.due_date;
        v_late_fee := 150.00;  -- Flat PKR 150 per Murabaha agreement
        NEW.days_overdue := v_days_overdue;
        NEW.late_fee_amount := v_late_fee;
        INSERT INTO late_fee_charity_allocations(installment_id, loan_id, late_fee_amount, 
            charity_org_id, allocated_at)
        SELECT NEW.id, NEW.loan_id, v_late_fee, id, NOW()
        FROM charity_organizations WHERE is_active = TRUE AND approved_by_shariah_board = TRUE
        LIMIT 1;
    END IF;
    RETURN NEW;
END; $$;
    """)

    op.execute("""
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at := NOW(); RETURN NEW; END; $$;
    """)

    # Apply audit triggers
    sensitive_tables = [
        'users', 'loans', 'installments', 'payment_transactions', 'murabaha_contracts', 
        'wakalah_agreements', 'virtual_cards', 'credit_applications', 'credit_limit_history', 
        'risk_assessments', 'fraud_alerts', 'user_payment_methods',
        'user_bank_accounts', 'orders', 'chargebacks', 'refunds', 'late_fee_charity_allocations',
        'journal_entries', 'settlements', 'admin_users', 'roles', 'permissions', 'role_permissions',
        'system_settings', 'feature_flags', 'promotional_codes', 'user_consent_records',
        'data_deletion_requests'
    ]
    # Removed user_kyc_verifications as it wasn't listed as currently existing or created by me, but Wait, "user_kyc_verifications" is marked present in spec.
    present_sensitive_tables = [
        'users', 'loans', 'installments', 'payment_transactions', 'murabaha_contracts', 
        'wakalah_agreements', 'virtual_cards', 'credit_applications', 'credit_limit_history', 
        'risk_assessments', 'fraud_alerts', 'user_kyc_verifications', 'user_payment_methods',
        'user_bank_accounts', 'orders', 'chargebacks', 'refunds', 'late_fee_charity_allocations',
        'journal_entries', 'settlements', 'admin_users', 'roles', 'permissions', 'role_permissions',
        'system_settings', 'feature_flags', 'promotional_codes', 'user_consent_records',
        'data_deletion_requests'
    ]

    for table in present_sensitive_tables:
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{table}') THEN
                CREATE TRIGGER trg_audit_{table}
                AFTER INSERT OR UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION fn_log_audit();
            END IF;
        END $$;
        """)

    # Apply other specific triggers
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'orders') THEN
                CREATE TRIGGER trg_generate_order_number
                BEFORE INSERT ON orders
                FOR EACH ROW EXECUTE FUNCTION fn_generate_order_number();
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'loans') THEN
                CREATE TRIGGER trg_recalculate_credit
                AFTER INSERT OR UPDATE ON loans
                FOR EACH ROW EXECUTE FUNCTION fn_recalculate_available_credit();
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'installments') THEN
                CREATE TRIGGER trg_apply_late_fee
                BEFORE UPDATE ON installments
                FOR EACH ROW EXECUTE FUNCTION fn_apply_late_fee();
            END IF;
        END $$;
    """)

def downgrade() -> None:
    # 1. Drop trigger function calls
    sensitive_tables = [
        'users', 'loans', 'installments', 'payment_transactions', 'murabaha_contracts', 
        'wakalah_agreements', 'virtual_cards', 'credit_applications', 'credit_limit_history', 
        'risk_assessments', 'fraud_alerts', 'user_kyc_verifications', 'user_payment_methods',
        'user_bank_accounts', 'orders', 'chargebacks', 'refunds', 'late_fee_charity_allocations',
        'journal_entries', 'settlements', 'admin_users', 'roles', 'permissions', 'role_permissions',
        'system_settings', 'feature_flags', 'promotional_codes', 'user_consent_records',
        'data_deletion_requests'
    ]
    for table in sensitive_tables:
        op.execute(f"DROP TRIGGER IF EXISTS trg_audit_{table} ON {table};")
        
    op.execute("DROP TRIGGER IF EXISTS trg_generate_order_number ON orders;")
    op.execute("DROP TRIGGER IF EXISTS trg_recalculate_credit ON loans;")
    op.execute("DROP TRIGGER IF EXISTS trg_apply_late_fee ON installments;")

    op.execute("DROP FUNCTION IF EXISTS fn_log_audit();")
    op.execute("DROP FUNCTION IF EXISTS fn_generate_order_number();")
    op.execute("DROP SEQUENCE IF EXISTS seq_order_number;")
    op.execute("DROP FUNCTION IF EXISTS fn_recalculate_available_credit();")
    op.execute("DROP FUNCTION IF EXISTS fn_apply_late_fee();")
    op.execute("DROP FUNCTION IF EXISTS fn_set_updated_at();")

    op.drop_table("aml_suspicious_activity_reports")
    op.drop_table("consent_logs")
    op.drop_table("data_deletion_requests")
    op.drop_table("regulatory_reports")
    op.drop_table("audit_trails")
