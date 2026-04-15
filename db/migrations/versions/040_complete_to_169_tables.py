"""Complete Schema to 169 Tables — Final Domain Tables

Revision ID: 040_complete_to_169_tables
Revises: 039_missing_db_objects
Create Date: 2026-04-15 12:00:00.000000

Brings the total unique base-table count to 169 as specified in
DB Design Volume I (Section 1–15) and Volume II (Section 16–25).

Domain B — Credit & Risk          (+6): bureau_credit_reports,
    income_verification_records, credit_policy_rules,
    risk_score_components, watchlist_screening_logs,
    fraud_case_investigations

Domain D — Order & Purchase        (+4): virtual_card_transactions,
    checkout_sessions, order_approval_rules, merchant_checkout_configs

Domain E — Payment & Installment   (+4): payment_links,
    debt_collection_cases, payment_gateway_configs,
    installment_date_change_requests

Domain H — Financial Accounting    (+3): company_bank_accounts,
    profit_recognition_schedules, tax_gl_mappings

Domain I — Support & Communications (+3): notification_preferences,
    whatsapp_templates, support_escalation_rules

Running total after this migration: 169 base tables ✓
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '040_complete_to_169_tables'
down_revision: Union[str, None] = '039_missing_db_objects'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# UPGRADE
# ---------------------------------------------------------------------------
def upgrade() -> None:

    # ═══════════════════════════════════════════════════════════════════════
    # DOMAIN B — CREDIT & RISK  (+6 tables → total: 18)
    # ═══════════════════════════════════════════════════════════════════════

    # B-1: bureau_credit_reports
    # TASDEEQ / PBCL / ECIB credit bureau pull records.
    # Referenced by scheduled task 'monthly_credit_bureau_report' (§16.9).
    op.create_table(
        "bureau_credit_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("credit_application_id", sa.BigInteger(), nullable=True),
        sa.Column("bureau_name", sa.String(length=30), nullable=False),
        sa.Column("request_reference", sa.String(length=100), nullable=True),
        sa.Column("inquiry_type", sa.String(length=30), nullable=False,
                  server_default="full_report"),
        sa.Column("credit_score", sa.Integer(), nullable=True),
        sa.Column("default_count", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("active_loans_count", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("total_outstanding_pkr", sa.Numeric(14, 2), nullable=True),
        sa.Column("bureau_response_raw", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column("report_pdf_s3", sa.String(length=512), nullable=True),
        sa.Column("is_hard_inquiry", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("queried_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "bureau_name IN ('tasdeeq','pbcl','ecib','i2c','manual')",
            name="chk_bureau_credit_reports_bureau_name"),
        sa.CheckConstraint(
            "inquiry_type IN ('full_report','summary','identity_only')",
            name="chk_bureau_credit_reports_inquiry_type"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["credit_application_id"],
                                ["credit_applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_bcr_user_queried",
                    "bureau_credit_reports", ["user_id", "queried_at"])
    op.create_index("idx_bcr_app",
                    "bureau_credit_reports", ["credit_application_id"])

    # B-2: income_verification_records
    # Formal income verification (NADRA tax record, bank salary credits,
    # employer letter, or self-declared). Maps to credit underwriting.
    op.create_table(
        "income_verification_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("verification_method", sa.String(length=40), nullable=False),
        sa.Column("stated_monthly_income", sa.Numeric(14, 2), nullable=True),
        sa.Column("verified_monthly_income", sa.Numeric(14, 2), nullable=True),
        sa.Column("income_source", sa.String(length=50), nullable=True),
        sa.Column("employer_name", sa.String(length=200), nullable=True),
        sa.Column("employment_start_date", sa.Date(), nullable=True),
        sa.Column("verification_status", sa.String(length=20), nullable=False,
                  server_default="pending"),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("documents_s3", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "verification_method IN ('bank_statement','salary_slip',"
            "'nadra_tax_record','employer_letter','self_declared',"
            "'freelance_contract','rental_deed')",
            name="chk_ivr_method"),
        sa.CheckConstraint(
            "income_source IN ('employment','business','freelance',"
            "'rental','pension','agriculture','other')",
            name="chk_ivr_income_source"),
        sa.CheckConstraint(
            "verification_status IN ('pending','verified','rejected','expired')",
            name="chk_ivr_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["admin_users.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_ivr_user_id",
                    "income_verification_records", ["user_id"])
    op.create_index("idx_ivr_status",
                    "income_verification_records", ["verification_status"])

    # B-3: credit_policy_rules
    # Configurable underwriting policies (min scores, DTI limits, down-payment
    # bands). Loaded from DB into Redis at startup and refreshed nightly.
    op.create_table(
        "credit_policy_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_code", sa.String(length=50), nullable=False),
        sa.Column("rule_name", sa.String(length=200), nullable=False),
        sa.Column("rule_category", sa.String(length=50), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False,
                  comment="e.g., {min_credit_score:600, max_dti:0.4}"),
        sa.Column("action", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False,
                  comment="e.g., {max_credit_limit:100000, min_down_pct:0.25}"),
        sa.Column("priority", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("5")),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "rule_category IN ('eligibility','credit_limit','down_payment',"
            "'term','interest_rate','blacklist','collection')",
            name="chk_cpr_category"),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 10",
            name="chk_cpr_priority"),
        sa.ForeignKeyConstraint(["approved_by"], ["admin_users.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_code"),
    )
    op.create_index("idx_cpr_category_active",
                    "credit_policy_rules", ["rule_category", "is_active"])

    # Seed initial credit policy rules
    op.execute("""
        INSERT INTO credit_policy_rules
            (rule_code, rule_name, rule_category, conditions, action,
             priority, effective_from)
        VALUES
        ('ELIG-001','Minimum Age Requirement','eligibility',
         '{"min_age_years": 21}', '{"block": true, "reason": "underage"}',
         1, CURRENT_DATE),
        ('ELIG-002','Minimum Credit Score — Onboarding','eligibility',
         '{"min_credit_score": 500}',
         '{"reject": true, "reason": "credit_score_too_low"}',
         2, CURRENT_DATE),
        ('ELIG-003','Max Active Loans','eligibility',
         '{"max_active_loans": 2}',
         '{"reject": true, "reason": "too_many_active_loans"}',
         3, CURRENT_DATE),
        ('CL-001','Max Credit Limit — Standard','credit_limit',
         '{"risk_band": ["A","B","C"]}',
         '{"max_credit_limit": 150000}',
         5, CURRENT_DATE),
        ('CL-002','Max Credit Limit — High Risk','credit_limit',
         '{"risk_band": ["D","E"]}',
         '{"max_credit_limit": 50000}',
         5, CURRENT_DATE),
        ('DP-001','Down Payment — Risk Band D','down_payment',
         '{"risk_band": ["D"]}',
         '{"min_down_payment_pct": 30}',
         5, CURRENT_DATE),
        ('DP-002','Down Payment — Risk Band E/F','down_payment',
         '{"risk_band": ["E","F"]}',
         '{"min_down_payment_pct": 50}',
         5, CURRENT_DATE)
        ON CONFLICT (rule_code) DO NOTHING
    """)

    # B-4: risk_score_components
    # Per-factor granular breakdown of each risk assessment.
    # Enables explainability and Shariah/SECP audit of credit decisions.
    op.create_table(
        "risk_score_components",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("risk_assessment_id", sa.BigInteger(), nullable=False),
        sa.Column("component_name", sa.String(length=50), nullable=False),
        sa.Column("raw_score", sa.Numeric(8, 4), nullable=False),
        sa.Column("weighted_score", sa.Numeric(8, 4), nullable=False),
        sa.Column("component_weight", sa.Numeric(5, 4), nullable=False),
        sa.Column("signal_details", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "component_name IN ('identity','device','behavioral',"
            "'bank_statement','bureau','velocity','geolocation',"
            "'network','repayment_history','alternative_data')",
            name="chk_rsc_component_name"),
        sa.CheckConstraint(
            "component_weight BETWEEN 0 AND 1",
            name="chk_rsc_weight"),
        sa.ForeignKeyConstraint(["risk_assessment_id"],
                                ["risk_assessments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_rsc_assessment",
                    "risk_score_components", ["risk_assessment_id"])

    # B-5: watchlist_screening_logs
    # UNSCR / NACTA / OFAC / EU sanctions screening log.
    # Required by SBP AML/CFT Guidelines and FATF compliance (Vol2 §23.6).
    op.create_table(
        "watchlist_screening_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("screening_type", sa.String(length=30), nullable=False),
        sa.Column("lists_checked", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("is_match", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("match_details", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column("resolution", sa.String(length=30), nullable=True),
        sa.Column("screened_by", sa.String(length=20), nullable=False,
                  server_default="system"),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("screened_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "screening_type IN ('onboarding','periodic','transaction','ad_hoc')",
            name="chk_wsl_type"),
        sa.CheckConstraint(
            "resolution IN ('cleared','false_positive','true_positive',"
            "'pending') OR resolution IS NULL",
            name="chk_wsl_resolution"),
        sa.CheckConstraint(
            "screened_by IN ('system','manual')",
            name="chk_wsl_screened_by"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["admin_users.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_wsl_user_screened",
                    "watchlist_screening_logs", ["user_id", "screened_at"])
    op.create_index("idx_wsl_is_match",
                    "watchlist_screening_logs", ["is_match"],
                    postgresql_where=sa.text("is_match = TRUE"))

    # B-6: fraud_case_investigations
    # Formal case management for escalated fraud_alerts.
    # Links to fraud_alerts and tracks evidence, financials, resolution.
    op.create_table(
        "fraud_case_investigations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_number", sa.String(length=40), nullable=False),
        sa.Column("alert_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("case_type", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("3")),
        sa.Column("status", sa.String(length=40), nullable=False,
                  server_default="investigating"),
        sa.Column("investigator_id", sa.BigInteger(), nullable=True),
        sa.Column("evidence_doc_s3", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("action_taken", sa.String(length=60), nullable=True),
        sa.Column("financial_impact", sa.Numeric(14, 2), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "case_type IN ('identity_theft','first_party_fraud',"
            "'synthetic_identity','account_takeover','collusion',"
            "'payment_fraud','document_forgery')",
            name="chk_fci_case_type"),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 5",
            name="chk_fci_priority"),
        sa.CheckConstraint(
            "status IN ('investigating','escalated_to_leo','suspended',"
            "'closed_genuine','closed_fraud','closed_false_positive')",
            name="chk_fci_status"),
        sa.CheckConstraint(
            "action_taken IN ('account_suspended','loan_written_off',"
            "'police_report_filed','amount_recovered','no_action') "
            "OR action_taken IS NULL",
            name="chk_fci_action"),
        sa.ForeignKeyConstraint(["alert_id"], ["fraud_alerts.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["investigator_id"], ["admin_users.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("case_number"),
    )
    op.create_index("idx_fci_user",
                    "fraud_case_investigations", ["user_id"])
    op.create_index("idx_fci_status_priority",
                    "fraud_case_investigations", ["status", "priority"])
    op.create_index("idx_fci_investigator",
                    "fraud_case_investigations", ["investigator_id", "status"])

    # ═══════════════════════════════════════════════════════════════════════
    # DOMAIN D — ORDER & PURCHASE  (+4 tables → total: 14)
    # ═══════════════════════════════════════════════════════════════════════

    # D-1: merchant_checkout_configs
    # Per-merchant Playwright automation configuration: script location,
    # cart/checkout URLs, CAPTCHA type, OTP handling. Referenced by the
    # agentic checkout service.
    op.create_table(
        "merchant_checkout_configs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("merchant_id", sa.BigInteger(), nullable=False),
        sa.Column("checkout_type", sa.String(length=20), nullable=False,
                  server_default="scraper_agent"),
        sa.Column("automation_script_s3", sa.String(length=512), nullable=True),
        sa.Column("script_version", sa.String(length=20), nullable=True),
        sa.Column("cart_url_template", sa.String(length=1024), nullable=True),
        sa.Column("checkout_url_template", sa.String(length=1024), nullable=True),
        sa.Column("payment_page_selector", sa.String(length=255), nullable=True),
        sa.Column("otp_required", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("captcha_type", sa.String(length=20), nullable=False,
                  server_default="none"),
        sa.Column("avg_checkout_seconds", sa.SmallInteger(), nullable=True),
        sa.Column("success_rate_30d", sa.Numeric(5, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("config_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "checkout_type IN ('direct','api','scraper_agent','manual')",
            name="chk_mcc_type"),
        sa.CheckConstraint(
            "captcha_type IN ('none','recaptcha_v2','recaptcha_v3',"
            "'hcaptcha','image','cloudflare')",
            name="chk_mcc_captcha"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_id"),
    )
    op.create_index("idx_mcc_active",
                    "merchant_checkout_configs", ["is_active"])

    # D-2: checkout_sessions
    # Tracks the agentic purchase session lifecycle from VCN issuance through
    # purchase confirmation. Supports crash recovery (checkpoint_data JSONB).
    op.create_table(
        "checkout_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("execution_id", sa.BigInteger(), nullable=True),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("session_status", sa.String(length=30), nullable=False,
                  server_default="initializing"),
        sa.Column("browser_fingerprint", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column("checkpoint_data", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True,
                  comment="Playwright session state for crash recovery"),
        sa.Column("screenshot_s3", sa.String(length=512), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failure_code", sa.String(length=50), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "session_status IN ('initializing','navigating','filling_form',"
            "'waiting_otp','payment_processing','completing','succeeded',"
            "'failed','abandoned','timed_out')",
            name="chk_cs_status"),
        # Foreign keys to partitioned tables (orders, purchase_executions) removed
        # as Postgres does not allow FKs to partitioned tables without including partition keys.
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_cs_order",
                    "checkout_sessions", ["order_id"])
    op.create_index("idx_cs_worker",
                    "checkout_sessions", ["worker_id", "session_status"])

    # D-3: virtual_card_transactions
    # VCN authorization/capture/void/refund events streamed from Lithic/Stripe
    # webhooks. Separate from payment_transactions (user-payment side).
    op.create_table(
        "virtual_card_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("virtual_card_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("issuer_transaction_id", sa.String(length=100), nullable=True),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False,
                  server_default="PKR"),
        sa.Column("merchant_name", sa.String(length=255), nullable=True),
        sa.Column("merchant_mcc", sa.String(length=4), nullable=True),
        sa.Column("is_mcc_allowed", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decline_reason", sa.String(length=100), nullable=True),
        sa.Column("issuer_raw_data", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column("authorized_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "transaction_type IN ('authorization','capture','void',"
            "'refund','chargeback','adjustment')",
            name="chk_vct_type"),
        sa.CheckConstraint(
            "status IN ('approved','declined','pending','reversed','settled')",
            name="chk_vct_status"),
        sa.ForeignKeyConstraint(["virtual_card_id"], ["virtual_cards.id"],
                                ondelete="RESTRICT"),
        # Foreign key to partitioned table (orders) removed to avoid Postgres limitations.
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("issuer_transaction_id"),
    )
    op.create_index("idx_vct_card",
                    "virtual_card_transactions", ["virtual_card_id",
                                                  "authorized_at"])
    op.create_index("idx_vct_status",
                    "virtual_card_transactions", ["status"],
                    postgresql_where=sa.text("status = 'declined'"))

    # D-4: order_approval_rules
    # Auto-approval rule engine configuration.  Defines which orders can be
    # approved automatically vs which require manual review.
    op.create_table(
        "order_approval_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_code", sa.String(length=50), nullable=False),
        sa.Column("rule_name", sa.String(length=200), nullable=False),
        sa.Column("applies_to", sa.String(length=40), nullable=False,
                  server_default="all_orders"),
        sa.Column("auto_approve_below_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("requires_manual_review", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("min_required_down_payment_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("block_if_any_overdue", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("block_if_active_fraud_alert", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("valid_risk_bands", postgresql.ARRAY(sa.Text()), nullable=True,
                  comment="NULL = all bands allowed"),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("priority", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("5")),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "applies_to IN ('all_orders','high_value','new_user',"
            "'risk_band_d','risk_band_e','risk_band_f','repeat_user')",
            name="chk_oar_applies_to"),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 10",
            name="chk_oar_priority"),
        sa.ForeignKeyConstraint(["updated_by"], ["admin_users.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_code"),
    )
    op.create_index("idx_oar_active_priority",
                    "order_approval_rules", ["is_active", "priority"])

    # Seed default rules
    op.execute("""
        INSERT INTO order_approval_rules
            (rule_code, rule_name, applies_to, auto_approve_below_amount,
             requires_manual_review, block_if_any_overdue,
             block_if_active_fraud_alert, priority)
        VALUES
        ('OAR-DEFAULT','Standard Auto-Approval','all_orders',
         30000.00, FALSE, TRUE, TRUE, 5),
        ('OAR-HIGH-VALUE','High-Value Manual Review','high_value',
         NULL, TRUE, TRUE, TRUE, 1),
        ('OAR-NEW-USER','New User Conservative Policy','new_user',
         15000.00, FALSE, TRUE, TRUE, 2)
        ON CONFLICT (rule_code) DO NOTHING
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # DOMAIN E — PAYMENT & INSTALLMENT  (+4 tables → total: 18)
    # ═══════════════════════════════════════════════════════════════════════

    # E-1: payment_links
    # Tokenized payment URLs sent via SMS/email/WhatsApp for due installments.
    # Redeemable once; expire after configurable TTL.
    op.create_table(
        "payment_links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("link_token", sa.String(length=64), nullable=False),
        sa.Column("installment_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("gateway", sa.String(length=30), nullable=True,
                  comment="Pre-selected gateway; NULL = user chooses"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("sent_via", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("first_clicked_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("payment_txn_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "gateway IN ('safepay','jazzcash','easypaisa','raast','stripe') "
            "OR gateway IS NULL",
            name="chk_pl_gateway"),
        sa.ForeignKeyConstraint(["installment_id"], ["installments.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("link_token"),
    )
    op.create_index("idx_pl_installment",
                    "payment_links", ["installment_id"],
                    postgresql_where=sa.text("is_active = TRUE"))
    op.create_index("idx_pl_user_active",
                    "payment_links", ["user_id", "is_active"])

    # E-2: debt_collection_cases
    # Escalated collection cases for non-performing loans.
    # Tracks collection stage, agent assignment, and last contact attempt.
    op.create_table(
        "debt_collection_cases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_number", sa.String(length=40), nullable=False),
        sa.Column("loan_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("total_overdue_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("overdue_days", sa.Integer(), nullable=False),
        sa.Column("collection_stage", sa.String(length=30), nullable=False,
                  server_default="early_delinquency"),
        sa.Column("assigned_agent_id", sa.BigInteger(), nullable=True),
        sa.Column("arrangement_id", sa.BigInteger(), nullable=True),
        sa.Column("last_contact_at", sa.DateTime(), nullable=True),
        sa.Column("next_action_at", sa.DateTime(), nullable=True),
        sa.Column("contact_attempts", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="active"),
        sa.Column("opened_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "collection_stage IN ('early_delinquency','late_delinquency',"
            "'pre_legal','legal','written_off')",
            name="chk_dcc_stage"),
        sa.CheckConstraint(
            "status IN ('active','resolved','written_off','legal_action')",
            name="chk_dcc_status"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_agent_id"], ["admin_users.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["arrangement_id"], ["payment_arrangements.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("case_number"),
    )
    op.create_index("idx_dcc_loan",
                    "debt_collection_cases", ["loan_id"])
    op.create_index("idx_dcc_agent_status",
                    "debt_collection_cases", ["assigned_agent_id", "status"])
    op.create_index("idx_dcc_stage_status",
                    "debt_collection_cases", ["collection_stage", "status"])

    # E-3: payment_gateway_configs
    # Per-gateway configuration: API credentials (encrypted), fee structures,
    # fallback routing priority. Replaces hardcoded gateway logic.
    op.create_table(
        "payment_gateway_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("gateway_code", sa.String(length=30), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("is_primary", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("routing_priority", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("5")),
        sa.Column("api_endpoint", sa.String(length=512), nullable=True),
        sa.Column("api_key_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("merchant_id_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("webhook_secret_hash", sa.String(length=64), nullable=True),
        sa.Column("transaction_fee_pct", sa.Numeric(5, 4), nullable=True),
        sa.Column("fixed_fee_pkr", sa.Numeric(10, 2), nullable=True),
        sa.Column("min_transaction_pkr", sa.Numeric(14, 2), nullable=True),
        sa.Column("max_transaction_pkr", sa.Numeric(14, 2), nullable=True),
        sa.Column("supports_refund", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("supports_partial_refund", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("settlement_days", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("2")),
        sa.Column("currency", sa.CHAR(length=3), nullable=False,
                  server_default="PKR"),
        sa.Column("environment", sa.String(length=10), nullable=False,
                  server_default="sandbox"),
        sa.Column("failure_count_24h", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("last_health_check_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "gateway_code IN ('safepay','jazzcash','easypaisa','raast',"
            "'stripe','nayapay','sadapay','manual')",
            name="chk_pgc_code"),
        sa.CheckConstraint(
            "environment IN ('sandbox','production')",
            name="chk_pgc_env"),
        sa.CheckConstraint(
            "routing_priority BETWEEN 1 AND 10",
            name="chk_pgc_priority"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gateway_code"),
    )

    # Seed payment gateway configs (credentials filled post-deploy)
    op.execute("""
        INSERT INTO payment_gateway_configs
            (gateway_code, display_name, routing_priority, transaction_fee_pct,
             fixed_fee_pkr, supports_refund, settlement_days, environment)
        VALUES
        ('safepay',   'Safepay',          1, 0.020, 0.00, TRUE,  2, 'sandbox'),
        ('jazzcash',  'JazzCash',         2, 0.015, 0.00, TRUE,  3, 'sandbox'),
        ('easypaisa', 'EasyPaisa',        3, 0.015, 0.00, FALSE, 3, 'sandbox'),
        ('raast',     'Raast (SBP IBFT)', 4, 0.000, 0.00, FALSE, 1, 'sandbox'),
        ('nayapay',   'NayaPay',          5, 0.010, 0.00, TRUE,  2, 'sandbox'),
        ('sadapay',   'SadaPay',          6, 0.010, 0.00, TRUE,  2, 'sandbox'),
        ('stripe',    'Stripe (VCN)',     7, 0.025, 0.00, TRUE,  7, 'sandbox'),
        ('manual',    'Manual Payment',  10, 0.000, 0.00, FALSE, 0, 'sandbox')
        ON CONFLICT (gateway_code) DO NOTHING
    """)

    # E-4: installment_date_change_requests
    # Customer requests to shift a due date within Shariah-compliant
    # grace window (typically ≤7 days). Requires admin approval or
    # auto-approved based on order_approval_rules.
    op.create_table(
        "installment_date_change_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("installment_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("current_due_date", sa.Date(), nullable=False),
        sa.Column("requested_due_date", sa.Date(), nullable=False),
        sa.Column("days_shift", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="pending"),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("shariah_compliance_note", sa.Text(), nullable=True,
                  server_default="Date change only; instalment amount unchanged"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "days_shift BETWEEN -7 AND 7",
            name="chk_idcr_days_shift"),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','auto_approved',"
            "'cancelled')",
            name="chk_idcr_status"),
        sa.CheckConstraint(
            "requested_due_date != current_due_date",
            name="chk_idcr_different_dates"),
        sa.ForeignKeyConstraint(["installment_id"], ["installments.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["admin_users.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_idcr_installment",
                    "installment_date_change_requests", ["installment_id"])
    op.create_index("idx_idcr_status",
                    "installment_date_change_requests", ["status"],
                    postgresql_where=sa.text("status = 'pending'"))

    # ═══════════════════════════════════════════════════════════════════════
    # DOMAIN H — FINANCIAL ACCOUNTING  (+3 tables → total: 13)
    # ═══════════════════════════════════════════════════════════════════════

    # H-1: company_bank_accounts
    # SahulatKar's operational bank accounts: current, escrow (charity),
    # escrow (merchants), payroll. Used for reconciliation against
    # gateway_settlements and charity_disbursements.
    op.create_table(
        "company_bank_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_name", sa.String(length=100), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=False),
        sa.Column("iban", sa.String(length=34), nullable=False),
        sa.Column("account_type", sa.String(length=30), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False,
                  server_default="PKR"),
        sa.Column("gl_account_id", sa.Integer(), nullable=True,
                  comment="Links to ledger_accounts chart of accounts"),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("current_balance", sa.Numeric(16, 2), nullable=True,
                  comment="Synced from bank portal/API; not authoritative"),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("purpose_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "account_type IN ('current','saving','escrow_charity',"
            "'escrow_merchant','payroll','reserve')",
            name="chk_cba_type"),
        sa.ForeignKeyConstraint(["gl_account_id"], ["ledger_accounts.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("iban"),
    )

    # H-2: profit_recognition_schedules
    # Murabaha profit recognition schedule (IFRS 9 / AAOIFI standard).
    # Each installment earns a proportionate slice of the total Murabaha profit.
    # journal_entries are created as each installment is collected.
    op.create_table(
        "profit_recognition_schedules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("loan_id", sa.BigInteger(), nullable=False),
        sa.Column("murabaha_contract_id", sa.BigInteger(), nullable=True),
        sa.Column("installment_id", sa.BigInteger(), nullable=True),
        sa.Column("installment_number", sa.SmallInteger(), nullable=False),
        sa.Column("recognition_date", sa.Date(), nullable=False),
        sa.Column("total_profit_on_contract", sa.Numeric(14, 2), nullable=False,
                  comment="Total Murabaha profit for this contract"),
        sa.Column("installment_profit_portion", sa.Numeric(14, 2), nullable=False,
                  comment="Profit slice allocated to this installment"),
        sa.Column("cumulative_recognized", sa.Numeric(14, 2), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("remaining_unrecognized", sa.Numeric(14, 2), nullable=False),
        sa.Column("recognition_method", sa.String(length=20), nullable=False,
                  server_default="straight_line"),
        sa.Column("journal_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("is_recognized", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("recognized_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "recognition_method IN ('straight_line','effective_interest',"
            "'rule_of_78','actual')",
            name="chk_prs_method"),
        sa.CheckConstraint(
            "installment_profit_portion >= 0",
            name="chk_prs_positive_profit"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["murabaha_contract_id"],
                                ["murabaha_contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["installment_id"], ["installments.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("loan_id", "installment_number",
                            name="uq_prs_loan_installment"),
    )
    op.create_index("idx_prs_loan",
                    "profit_recognition_schedules", ["loan_id"])
    op.create_index("idx_prs_unrecognized",
                    "profit_recognition_schedules", ["is_recognized",
                                                     "recognition_date"],
                    postgresql_where=sa.text("is_recognized = FALSE"))

    # H-3: tax_gl_mappings
    # Maps each tax type to its corresponding General Ledger account.
    # Used by the billing engine to automatically create tax journal entries.
    # Covers FBR GST, WHT, Income Tax, Stamp Duty.
    op.create_table(
        "tax_gl_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tax_type", sa.String(length=40), nullable=False),
        sa.Column("tax_name", sa.String(length=100), nullable=False),
        sa.Column("gl_account_id", sa.Integer(), nullable=False),
        sa.Column("tax_rate_pct", sa.Numeric(6, 4), nullable=False),
        sa.Column("applicable_threshold_pkr", sa.Numeric(14, 2), nullable=True,
                  comment="Transaction value above which this tax applies"),
        sa.Column("applicable_to", sa.String(length=100), nullable=False,
                  comment="e.g. profit_income, merchant_payments, salary"),
        sa.Column("fbr_tax_code", sa.String(length=20), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "tax_type IN ('gst_on_services','income_tax','wht_on_services',"
            "'wht_on_supplies','advance_income_tax','stamp_duty',"
            "'super_tax','workers_welfare_fund')",
            name="chk_tgm_tax_type"),
        sa.CheckConstraint(
            "tax_rate_pct >= 0 AND tax_rate_pct <= 100",
            name="chk_tgm_rate"),
        sa.ForeignKeyConstraint(["gl_account_id"], ["ledger_accounts.id"],
                                ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tax_type", "effective_from",
                            name="uq_tgm_type_date"),
    )

    # ═══════════════════════════════════════════════════════════════════════
    # DOMAIN I — SUPPORT & COMMUNICATIONS  (+3 tables → total: 12)
    # ═══════════════════════════════════════════════════════════════════════

    # I-1: notification_preferences
    # Per-user notification opt-in/opt-out settings.
    # One row per user; covers all channels and notification types.
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("sms_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("email_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("push_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("whatsapp_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("marketing_sms", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("marketing_email", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("payment_reminders", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("delivery_updates", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("account_security_alerts", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("preferred_language", sa.CHAR(length=2), nullable=False,
                  server_default="en"),
        sa.Column("quiet_hours_start", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("22"),
                  comment="Hour 0-23 in PKT when to suppress non-critical notifications"),
        sa.Column("quiet_hours_end", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("8")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "preferred_language IN ('en','ur')",
            name="chk_np_language"),
        sa.CheckConstraint(
            "quiet_hours_start BETWEEN 0 AND 23",
            name="chk_np_quiet_start"),
        sa.CheckConstraint(
            "quiet_hours_end BETWEEN 0 AND 23",
            name="chk_np_quiet_end"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    # I-2: whatsapp_templates
    # Meta-approved WhatsApp Business API message templates.
    # Required before sending transactional messages on WhatsApp channel
    # (notifications_queue channel='whatsapp'). Stores Meta API template IDs.
    op.create_table(
        "whatsapp_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_code", sa.String(length=100), nullable=False,
                  comment="Internal code matching notification_type in notifications_queue"),
        sa.Column("wa_template_id", sa.String(length=100), nullable=True,
                  comment="Meta-assigned template ID after approval"),
        sa.Column("namespace", sa.String(length=100), nullable=True,
                  comment="WhatsApp Business namespace"),
        sa.Column("language", sa.String(length=5), nullable=False,
                  server_default="en_PK"),
        sa.Column("category", sa.String(length=20), nullable=False,
                  server_default="utility"),
        sa.Column("header_type", sa.String(length=20), nullable=False,
                  server_default="none"),
        sa.Column("header_text", sa.String(length=255), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False,
                  comment="Template text with {{1}}, {{2}} variable placeholders"),
        sa.Column("footer_text", sa.String(length=100), nullable=True),
        sa.Column("button_configs", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column("variable_count", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="pending"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "category IN ('authentication','utility','marketing')",
            name="chk_wt_category"),
        sa.CheckConstraint(
            "header_type IN ('none','text','image','document','video')",
            name="chk_wt_header"),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','paused','disabled')",
            name="chk_wt_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_code", "language",
                            name="uq_wt_code_lang"),
    )
    op.create_index("idx_wt_active",
                    "whatsapp_templates", ["is_active"],
                    postgresql_where=sa.text("is_active = TRUE"))

    # Seed WhatsApp templates (submit to Meta for approval post-launch)
    op.execute("""
        INSERT INTO whatsapp_templates
            (template_code, language, category, header_type,
             body_template, variable_count, status)
        VALUES
        ('payment_due_reminder','en_PK','utility','none',
         'Assalam-u-Alaikum! Your SahulatKar instalment of PKR {{1}} is due on {{2}}. Pay now: {{3}}',
         3, 'pending'),
        ('payment_due_reminder','ur_PK','utility','none',
         'السلام علیکم! آپ کی قسط PKR {{1}} کی ادائیگی {{2}} کو واجب ہے۔',
         2, 'pending'),
        ('order_confirmed','en_PK','utility','none',
         'Order confirmed! Your SahulatKar order {{1}} for {{2}} has been placed. Track at: {{3}}',
         3, 'pending'),
        ('otp_verification','en_PK','authentication','none',
         'Your SahulatKar OTP is {{1}}. Valid for 3 minutes. Do not share.',
         1, 'pending'),
        ('payment_received','en_PK','utility','none',
         'Payment received! PKR {{1}} credited for order {{2}}. Thank you.',
         2, 'pending')
        ON CONFLICT (template_code, language) DO NOTHING
    """)

    # I-3: support_escalation_rules
    # Configurable auto-escalation matrix for support tickets.
    # Triggers define when escalation fires; actions define what changes.
    op.create_table(
        "support_escalation_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_name", sa.String(length=100), nullable=False),
        sa.Column("trigger_condition", sa.String(length=50), nullable=False),
        sa.Column("source_category", sa.String(length=50), nullable=True,
                  comment="NULL = applies to all categories"),
        sa.Column("source_status", sa.String(length=50), nullable=True,
                  comment="NULL = any status"),
        sa.Column("threshold_minutes", sa.Integer(), nullable=True,
                  comment="For time-based triggers: minutes elapsed"),
        sa.Column("target_status", sa.String(length=30), nullable=False),
        sa.Column("target_priority", sa.String(length=10), nullable=True),
        sa.Column("target_assignee_role", sa.String(length=50), nullable=True),
        sa.Column("notify_admin_ids", postgresql.ARRAY(sa.BigInteger()),
                  nullable=True),
        sa.Column("add_internal_note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "trigger_condition IN ('sla_approaching','sla_breached',"
            "'priority_urgent','keyword_match','user_vip','repeat_contact',"
            "'no_response_24h','high_satisfaction_risk')",
            name="chk_ser_trigger"),
        sa.CheckConstraint(
            "target_status IN ('in_progress','waiting_user','escalated',"
            "'resolved','closed')",
            name="chk_ser_target_status"),
        sa.CheckConstraint(
            "target_priority IN ('low','medium','high','urgent') "
            "OR target_priority IS NULL",
            name="chk_ser_target_priority"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_name"),
    )

    # Seed common escalation rules
    op.execute("""
        INSERT INTO support_escalation_rules
            (rule_name, trigger_condition, threshold_minutes,
             target_status, target_priority, is_active)
        VALUES
        ('SLA Breach Auto-Escalate','sla_breached',
         0, 'escalated', 'urgent', TRUE),
        ('24h No Agent Response','no_response_24h',
         1440, 'escalated', 'high', TRUE),
        ('Urgent Priority Immediate Escalate','priority_urgent',
         0, 'escalated', 'urgent', TRUE),
        ('SLA Approaching 2h Warning','sla_approaching',
         120, 'in_progress', 'high', TRUE)
        ON CONFLICT (rule_name) DO NOTHING
    """)


# ---------------------------------------------------------------------------
# DOWNGRADE
# ---------------------------------------------------------------------------
def downgrade() -> None:
    # Domain I
    op.drop_table("support_escalation_rules")
    op.drop_table("whatsapp_templates")
    op.drop_table("notification_preferences")

    # Domain H
    op.drop_table("tax_gl_mappings")
    op.drop_table("profit_recognition_schedules")
    op.drop_table("company_bank_accounts")

    # Domain E
    op.drop_table("installment_date_change_requests")
    op.drop_table("payment_gateway_configs")
    op.drop_table("debt_collection_cases")
    op.drop_table("payment_links")

    # Domain D
    op.drop_table("order_approval_rules")
    op.drop_table("virtual_card_transactions")
    op.drop_table("checkout_sessions")
    op.drop_table("merchant_checkout_configs")

    # Domain B
    op.drop_table("fraud_case_investigations")
    op.drop_table("watchlist_screening_logs")
    op.drop_table("risk_score_components")
    op.drop_table("credit_policy_rules")
    op.drop_table("income_verification_records")
    op.drop_table("bureau_credit_reports")
