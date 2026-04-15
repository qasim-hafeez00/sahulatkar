"""Missing Domain Tables

Revision ID: 038_missing_domain_tables
Revises: 037_reapply_triggers
Create Date: 2026-04-15 08:30:00.000000

Adds all domain tables identified in the DB Gap Analysis (April 2026):
  Domain A  — MED-A01 pk_mobile_prefixes, MED-A02 cnic_division_codes
  Domain E  — CRIT-E01 payment_plan_configurations, MED-E02 loan_loss_provisions,
               MED-E03 write_off_records
  Domain F  — MED-F01 delivery_zones, MED-F02 delivery_sla_configs
  Domain G  — MED-G01 murabaha_contract_templates, MED-G02 charity_disbursements
  Domain H  — MED-H01 tax_filings, MED-H02 balance_sheet_snapshots
  Domain I  — MED-I01 chatbot_sessions, MED-I02 support_ticket_sla_configs
  Domain J  — MED-J01 user_segments + campaign_segments
  Domain L  — MED-L01 regulatory_calendar, MED-L02 pci_dss_assessments,
               MED-L03 secp_filings
  Domain M  — MED-M01 third_party_service_configs, MED-M02 rate_limit_configs,
               MED-M03 scheduled_task_runs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '038_missing_domain_tables'
down_revision: Union[str, None] = '037_reapply_triggers'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # DOMAIN A — User & Identity
    # =========================================================================

    # MED-A01: pk_mobile_prefixes
    # Routes users to the correct mobile wallet during payment flow.
    op.execute("""
        CREATE TABLE IF NOT EXISTS pk_mobile_prefixes (
            prefix              VARCHAR(7)  PRIMARY KEY,
            operator            VARCHAR(20) NOT NULL
                CHECK (operator IN ('jazz','telenor','zong','ufone','warid')),
            supports_jazzcash   BOOLEAN     NOT NULL DEFAULT FALSE,
            supports_easypaisa  BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at          TIMESTAMP   NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pk_mobile_prefixes_operator
            ON pk_mobile_prefixes (operator);
    """)
    op.execute("""
        INSERT INTO pk_mobile_prefixes (prefix, operator, supports_jazzcash, supports_easypaisa) VALUES
            ('+92300','jazz',    true,  false),('+92301','jazz',    true,  false),
            ('+92302','jazz',    true,  false),('+92303','jazz',    true,  false),
            ('+92304','jazz',    true,  false),('+92305','jazz',    true,  false),
            ('+92306','jazz',    true,  false),('+92307','jazz',    true,  false),
            ('+92308','jazz',    true,  false),('+92309','jazz',    true,  false),
            ('+92340','jazz',    true,  false),('+92341','jazz',    true,  false),
            ('+92345','telenor', false, true), ('+92346','telenor', false, true),
            ('+92347','telenor', false, true), ('+92348','telenor', false, true),
            ('+92349','telenor', false, true), ('+92311','zong',    false, false),
            ('+92312','zong',    false, false),('+92313','zong',    false, false),
            ('+92314','zong',    false, false),('+92315','zong',    false, false),
            ('+92316','zong',    false, false),('+92317','zong',    false, false),
            ('+92318','zong',    false, false),('+92319','zong',    false, false),
            ('+92321','ufone',   false, false),('+92322','ufone',   false, false),
            ('+92323','ufone',   false, false),('+92324','ufone',   false, false),
            ('+92325','ufone',   false, false)
        ON CONFLICT (prefix) DO NOTHING;
    """)

    # MED-A02: cnic_division_codes
    # Province-level lookup from CNIC's 5-digit division prefix.
    op.execute("""
        CREATE TABLE IF NOT EXISTS cnic_division_codes (
            division_code  CHAR(5)      PRIMARY KEY,
            province       VARCHAR(50)  NOT NULL
                CHECK (province IN (
                    'Sindh','Punjab','KPK','Balochistan',
                    'Gilgit-Baltistan','AJK','ICT'
                )),
            division_name  VARCHAR(100) NOT NULL,
            created_at     TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        INSERT INTO cnic_division_codes (division_code, province, division_name) VALUES
            ('35201','Punjab',      'Lahore'),
            ('35202','Punjab',      'Lahore (Central)'),
            ('42101','Sindh',       'Karachi (South)'),
            ('42201','Sindh',       'Karachi (West)'),
            ('61101','ICT',         'Islamabad'),
            ('13101','KPK',         'Peshawar'),
            ('52101','Balochistan', 'Quetta'),
            ('36101','Punjab',      'Faisalabad'),
            ('37101','Punjab',      'Rawalpindi'),
            ('36302','Punjab',      'Chiniot')
        ON CONFLICT (division_code) DO NOTHING;
    """)

    # =========================================================================
    # DOMAIN E — Payment & Installment
    # =========================================================================

    # CRIT-E01: payment_plan_configurations
    # Admin-configurable BNPL plan definitions consumed by credit engine,
    # ledger service, and contract service.
    op.execute("""
        CREATE TABLE IF NOT EXISTS payment_plan_configurations (
            id                    SERIAL        PRIMARY KEY,
            plan_code             VARCHAR(20)   NOT NULL UNIQUE,
            display_name          VARCHAR(50)   NOT NULL,
            down_payment_pct      DECIMAL(5,2)  NOT NULL,
            installment_count     SMALLINT      NOT NULL CHECK (installment_count BETWEEN 1 AND 12),
            installment_frequency VARCHAR(20)   NOT NULL
                CHECK (installment_frequency IN ('weekly','biweekly','monthly')),
            duration_days         SMALLINT      NOT NULL,
            murabaha_markup_pct   DECIMAL(5,2)  NOT NULL,
            min_order_amount      DECIMAL(14,2) NOT NULL DEFAULT 1500.00,
            max_order_amount      DECIMAL(14,2) NOT NULL DEFAULT 100000.00,
            status                VARCHAR(20)   NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','disabled','planned')),
            shariah_approved      BOOLEAN       NOT NULL DEFAULT FALSE,
            shariah_approval_ref  VARCHAR(50),
            updated_by            BIGINT        REFERENCES admin_users(id) ON DELETE SET NULL,
            created_at            TIMESTAMP     NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMP     NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        INSERT INTO payment_plan_configurations
            (plan_code, display_name, down_payment_pct, installment_count,
             installment_frequency, duration_days, murabaha_markup_pct,
             status, shariah_approved) VALUES
            ('pay_in_3',  'Pay in 3',   33.33,  2, 'biweekly', 42,  2.5,  'disabled', true),
            ('pay_in_4',  'Pay in 4',   25.00,  3, 'biweekly', 42,  4.0,  'active',   true),
            ('pay_in_6',  'Pay in 6',   16.67,  5, 'monthly',  150, 7.0,  'planned',  false),
            ('pay_in_12', 'Pay in 12',  10.00, 11, 'monthly',  330, 15.0, 'planned',  false)
        ON CONFLICT (plan_code) DO NOTHING;
    """)

    # MED-E02: loan_loss_provisions
    # IFRS 9 provisioning and SECP NBFC regulatory reporting.
    op.execute("""
        CREATE TABLE IF NOT EXISTS loan_loss_provisions (
            id                    BIGSERIAL     PRIMARY KEY,
            uuid                  UUID          NOT NULL DEFAULT gen_random_uuid(),
            provision_date        DATE          NOT NULL,
            portfolio_outstanding DECIMAL(14,2) NOT NULL,
            provision_rate_pct    DECIMAL(5,4)  NOT NULL DEFAULT 0.0200,
            provision_amount      DECIMAL(14,2) NOT NULL,
            actual_charge_offs    DECIMAL(14,2) NOT NULL DEFAULT 0,
            actual_recoveries     DECIMAL(14,2) NOT NULL DEFAULT 0,
            net_credit_loss       DECIMAL(14,2)
                GENERATED ALWAYS AS (actual_charge_offs - actual_recoveries) STORED,
            npl_ratio             DECIMAL(5,4),
            notes                 TEXT,
            generated_by          BIGINT        REFERENCES admin_users(id) ON DELETE SET NULL,
            created_at            TIMESTAMP     NOT NULL DEFAULT NOW(),
            UNIQUE (provision_date)
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_loan_loss_provisions_date
            ON loan_loss_provisions (provision_date DESC);
    """)

    # MED-E03: write_off_records
    # Internal accounting decision for 60+ day collections bucket.
    op.execute("""
        CREATE TABLE IF NOT EXISTS write_off_records (
            id                  BIGSERIAL     PRIMARY KEY,
            uuid                UUID          NOT NULL DEFAULT gen_random_uuid(),
            loan_id             BIGINT        NOT NULL REFERENCES loans(id) ON DELETE RESTRICT,
            user_id             BIGINT        NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            write_off_amount    DECIMAL(14,2) NOT NULL,
            write_off_date      DATE          NOT NULL,
            reason_code         VARCHAR(50)   NOT NULL,
            recovery_agent      VARCHAR(100),
            journal_entry_id    BIGINT        REFERENCES journal_entries(id) ON DELETE RESTRICT,
            approved_by         BIGINT        REFERENCES admin_users(id) ON DELETE SET NULL,
            tasdeeq_reported    BOOLEAN       NOT NULL DEFAULT FALSE,
            tasdeeq_reported_at TIMESTAMP,
            created_at          TIMESTAMP     NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_write_off_records_loan_id ON write_off_records (loan_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_write_off_records_date   ON write_off_records (write_off_date DESC);")

    # =========================================================================
    # DOMAIN F — Delivery & Logistics
    # =========================================================================

    # MED-F01: delivery_zones
    # Drives courier selection algorithm for routing per delivery area.
    op.execute("""
        CREATE TABLE IF NOT EXISTS delivery_zones (
            id                   SERIAL       PRIMARY KEY,
            zone_code            VARCHAR(20)  NOT NULL UNIQUE,
            zone_name            VARCHAR(100) NOT NULL,
            province             VARCHAR(50)  NOT NULL
                CHECK (province IN (
                    'Sindh','Punjab','KPK','Balochistan',
                    'Gilgit-Baltistan','AJK','ICT'
                )),
            cities               TEXT[],
            postal_codes         TEXT[],
            preferred_courier_id BIGINT       REFERENCES couriers(id) ON DELETE SET NULL,
            is_serviceable       BOOLEAN      NOT NULL DEFAULT TRUE,
            surcharge_pkr        DECIMAL(8,2) NOT NULL DEFAULT 0,
            est_delivery_days    SMALLINT     NOT NULL DEFAULT 3,
            created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_delivery_zones_province ON delivery_zones (province);")

    # MED-F02: delivery_sla_configs
    # Per-courier per-zone expected delivery windows for ETA calculations.
    op.execute("""
        CREATE TABLE IF NOT EXISTS delivery_sla_configs (
            id          SERIAL    PRIMARY KEY,
            courier_id  BIGINT    NOT NULL REFERENCES couriers(id) ON DELETE CASCADE,
            zone_id     INTEGER   NOT NULL REFERENCES delivery_zones(id) ON DELETE CASCADE,
            min_days    SMALLINT  NOT NULL DEFAULT 1,
            max_days    SMALLINT  NOT NULL DEFAULT 5,
            is_active   BOOLEAN   NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (courier_id, zone_id)
        );
    """)

    # =========================================================================
    # DOMAIN G — Shariah Compliance
    # =========================================================================

    # MED-G01: murabaha_contract_templates
    # Version-controlled Shariah board certified contract templates.
    op.execute("""
        CREATE TABLE IF NOT EXISTS murabaha_contract_templates (
            id                   SERIAL       PRIMARY KEY,
            uuid                 UUID         NOT NULL DEFAULT gen_random_uuid(),
            template_version     VARCHAR(10)  NOT NULL UNIQUE,
            template_name        VARCHAR(100) NOT NULL,
            wakalah_template_s3  VARCHAR(512) NOT NULL,
            murabaha_template_s3 VARCHAR(512) NOT NULL,
            shariah_approval_id  BIGINT       REFERENCES shariah_board_approvals(id),
            is_active            BOOLEAN      NOT NULL DEFAULT FALSE,
            effective_from       DATE         NOT NULL,
            effective_until      DATE,
            change_notes         TEXT,
            created_by           BIGINT       REFERENCES admin_users(id) ON DELETE SET NULL,
            created_at           TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)

    # MED-G02: charity_disbursements
    # Tracks actual batch disbursements to charity orgs (e.g., Edhi Foundation).
    op.execute("""
        CREATE TABLE IF NOT EXISTS charity_disbursements (
            id                   BIGSERIAL     PRIMARY KEY,
            uuid                 UUID          NOT NULL DEFAULT gen_random_uuid(),
            charity_org_id       BIGINT        NOT NULL REFERENCES charity_organizations(id),
            disbursement_period  VARCHAR(7)    NOT NULL,
            total_allocated_pkr  DECIMAL(14,2) NOT NULL,
            total_disbursed_pkr  DECIMAL(14,2) NOT NULL,
            allocation_ids       BIGINT[],
            bank_transfer_ref    VARCHAR(100),
            receipt_s3           VARCHAR(512),
            receipt_date         DATE,
            journal_entry_id     BIGINT        REFERENCES journal_entries(id),
            approved_by          BIGINT        REFERENCES admin_users(id) ON DELETE SET NULL,
            status               VARCHAR(20)   NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','disbursed','verified')),
            created_at           TIMESTAMP     NOT NULL DEFAULT NOW(),
            UNIQUE (charity_org_id, disbursement_period)
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_charity_disbursements_period
            ON charity_disbursements (disbursement_period DESC);
    """)

    # =========================================================================
    # DOMAIN H — Financial Accounting
    # =========================================================================

    # MED-H01: tax_filings
    # Tracks FBR obligations: GST-3, Income Tax, WHT per admin doc §6.5.
    op.execute("""
        CREATE TABLE IF NOT EXISTS tax_filings (
            id             BIGSERIAL    PRIMARY KEY,
            uuid           UUID         NOT NULL DEFAULT gen_random_uuid(),
            filing_type    VARCHAR(30)  NOT NULL
                CHECK (filing_type IN ('gst_3','income_tax_annual','wht_monthly','secp_nbfc_return')),
            period_start   DATE         NOT NULL,
            period_end     DATE         NOT NULL,
            taxable_amount DECIMAL(14,2),
            tax_amount     DECIMAL(14,2),
            status         VARCHAR(20)  NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','filed','accepted','under_review','revised')),
            fbr_reference  VARCHAR(100),
            filing_pdf_s3  VARCHAR(512),
            filed_at       TIMESTAMP,
            filed_by       BIGINT       REFERENCES admin_users(id) ON DELETE SET NULL,
            due_date       DATE         NOT NULL,
            created_at     TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tax_filings_type_period
            ON tax_filings (filing_type, period_start DESC);
    """)

    # MED-H02: balance_sheet_snapshots
    # Monthly snapshots for SECP NBFC regulatory and investor reporting.
    op.execute("""
        CREATE TABLE IF NOT EXISTS balance_sheet_snapshots (
            id                BIGSERIAL     PRIMARY KEY,
            snapshot_date     DATE          NOT NULL UNIQUE,
            total_assets      DECIMAL(14,2) NOT NULL,
            total_liabilities DECIMAL(14,2) NOT NULL,
            total_equity      DECIMAL(14,2) NOT NULL,
            loan_book_gross   DECIMAL(14,2) NOT NULL,
            loan_loss_reserve DECIMAL(14,2) NOT NULL,
            loan_book_net     DECIMAL(14,2) NOT NULL,
            cash_and_bank     DECIMAL(14,2) NOT NULL,
            data_snapshot     JSONB,
            generated_by      BIGINT        REFERENCES admin_users(id) ON DELETE SET NULL,
            created_at        TIMESTAMP     NOT NULL DEFAULT NOW()
        );
    """)

    # =========================================================================
    # DOMAIN I — Support & Communications
    # =========================================================================

    # MED-I01: chatbot_sessions
    # AI chatbot first-contact session tracking for CSAT and escalation analytics.
    op.execute("""
        CREATE TABLE IF NOT EXISTS chatbot_sessions (
            id                 BIGSERIAL    PRIMARY KEY,
            uuid               UUID         NOT NULL DEFAULT gen_random_uuid(),
            user_id            BIGINT       NOT NULL REFERENCES users(id),
            session_start      TIMESTAMP    NOT NULL DEFAULT NOW(),
            session_end        TIMESTAMP,
            message_count      SMALLINT     NOT NULL DEFAULT 0,
            escalated_to_human BOOLEAN      NOT NULL DEFAULT FALSE,
            escalation_reason  VARCHAR(100),
            resolved_by_bot    BOOLEAN      NOT NULL DEFAULT FALSE,
            ticket_id          BIGINT       REFERENCES support_tickets(id) ON DELETE SET NULL,
            sentiment_score    DECIMAL(4,3),
            created_at         TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_chatbot_sessions_user_id ON chatbot_sessions (user_id);")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chatbot_sessions_escalated
            ON chatbot_sessions (escalated_to_human)
            WHERE escalated_to_human = TRUE;
    """)

    # MED-I02: support_ticket_sla_configs
    # Admin-configurable per-category SLA targets from admin doc §7.2.
    op.execute("""
        CREATE TABLE IF NOT EXISTS support_ticket_sla_configs (
            id                  SERIAL      PRIMARY KEY,
            category            VARCHAR(50) NOT NULL UNIQUE
                CHECK (category IN (
                    'payment_issue','delivery_issue','product_issue',
                    'kyc_query','fraud_report','refund_request',
                    'contract_query','account_issue','general'
                )),
            priority            VARCHAR(10) NOT NULL
                CHECK (priority IN ('low','medium','high','urgent','critical')),
            first_response_mins INTEGER     NOT NULL,
            resolution_hours    INTEGER     NOT NULL,
            is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
            updated_by          BIGINT      REFERENCES admin_users(id) ON DELETE SET NULL,
            updated_at          TIMESTAMP   NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        INSERT INTO support_ticket_sla_configs
            (category, priority, first_response_mins, resolution_hours) VALUES
            ('payment_issue',  'critical', 15,  2),
            ('delivery_issue', 'high',     30,  4),
            ('account_issue',  'high',     30,  2),
            ('refund_request', 'high',     60,  24),
            ('kyc_query',      'medium',   120, 24),
            ('contract_query', 'medium',   120, 24),
            ('product_issue',  'medium',   60,  4),
            ('fraud_report',   'critical', 15,  2),
            ('general',        'low',      240, 24)
        ON CONFLICT (category) DO NOTHING;
    """)

    # =========================================================================
    # DOMAIN J — Marketing & Growth
    # =========================================================================

    # MED-J01: user_segments + campaign_segments
    # Re-usable user segment definitions with JSON filter criteria.
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_segments (
            id               BIGSERIAL    PRIMARY KEY,
            uuid             UUID         NOT NULL DEFAULT gen_random_uuid(),
            name             VARCHAR(100) NOT NULL UNIQUE,
            description      TEXT,
            filter_criteria  JSONB        NOT NULL,
            estimated_size   INTEGER,
            last_computed_at TIMESTAMP,
            is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
            created_by       BIGINT       REFERENCES admin_users(id) ON DELETE SET NULL,
            created_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS campaign_segments (
            campaign_id BIGINT NOT NULL REFERENCES marketing_campaigns(id) ON DELETE CASCADE,
            segment_id  BIGINT NOT NULL REFERENCES user_segments(id)       ON DELETE CASCADE,
            PRIMARY KEY (campaign_id, segment_id)
        );
    """)

    # =========================================================================
    # DOMAIN L — Compliance & Audit
    # =========================================================================

    # MED-L01: regulatory_calendar
    # Configuration table for all regulatory reporting obligations.
    op.execute("""
        CREATE TABLE IF NOT EXISTS regulatory_calendar (
            id                   SERIAL       PRIMARY KEY,
            report_code          VARCHAR(50)  NOT NULL UNIQUE,
            report_name          VARCHAR(200) NOT NULL,
            regulator            VARCHAR(20)  NOT NULL
                CHECK (regulator IN ('SBP','SECP','FBR','FMU','Shariah_Board','PCI_DSS')),
            frequency            VARCHAR(20)  NOT NULL
                CHECK (frequency IN ('monthly','quarterly','annual','as_needed')),
            due_day_of_month     SMALLINT,
            auto_generated       BOOLEAN      NOT NULL DEFAULT FALSE,
            reminder_days_before SMALLINT     NOT NULL DEFAULT 7,
            responsible_role     VARCHAR(50),
            notes                TEXT,
            is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at           TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        INSERT INTO regulatory_calendar
            (report_code, report_name, regulator, frequency, due_day_of_month, auto_generated) VALUES
            ('SBP_RCD1',  'Consumer Financing Return (RCD-1)', 'SBP',           'monthly',    5,    true),
            ('SECP_NBFC', 'NBFC Annual Return',                'SECP',          'annual',     NULL, false),
            ('FBR_GST3',  'Sales Tax Return (GST-3)',          'FBR',           'monthly',    15,   true),
            ('FBR_IT',    'Income Tax Return',                 'FBR',           'annual',     NULL, false),
            ('SHARIAH_Q', 'Shariah Compliance Report',         'Shariah_Board', 'quarterly',  15,   true),
            ('FMU_STR',   'Suspicious Transaction Report',     'FMU',           'as_needed',  NULL, false),
            ('FMU_CTR',   'Currency Transaction Report',       'FMU',           'as_needed',  NULL, false),
            ('PCI_DSS',   'PCI DSS Assessment',                'PCI_DSS',       'annual',     NULL, false)
        ON CONFLICT (report_code) DO NOTHING;
    """)

    # MED-L02: pci_dss_assessments
    # Card network compliance tracking (required for Stripe Issuing virtual cards).
    op.execute("""
        CREATE TABLE IF NOT EXISTS pci_dss_assessments (
            id                SERIAL      PRIMARY KEY,
            assessment_year   SMALLINT    NOT NULL,
            assessment_type   VARCHAR(20) NOT NULL DEFAULT 'SAQ_A_EP'
                CHECK (assessment_type IN ('SAQ_A','SAQ_A_EP','SAQ_D','QSA_ROC')),
            assessor_name     VARCHAR(200),
            status            VARCHAR(30) NOT NULL DEFAULT 'in_progress'
                CHECK (status IN ('in_progress','passed','failed','remediation')),
            report_s3         VARCHAR(512),
            aoc_s3            VARCHAR(512),
            valid_from        DATE,
            valid_until       DATE,
            findings_count    SMALLINT    NOT NULL DEFAULT 0,
            critical_findings SMALLINT    NOT NULL DEFAULT 0,
            created_at        TIMESTAMP   NOT NULL DEFAULT NOW(),
            UNIQUE (assessment_year, assessment_type)
        );
    """)

    # MED-L03: secp_filings
    # Tracks SECP IRIS portal submission metadata separate from regulatory_reports.
    op.execute("""
        CREATE TABLE IF NOT EXISTS secp_filings (
            id             BIGSERIAL    PRIMARY KEY,
            uuid           UUID         NOT NULL DEFAULT gen_random_uuid(),
            filing_type    VARCHAR(50)  NOT NULL,
            period_start   DATE         NOT NULL,
            period_end     DATE         NOT NULL,
            secp_reference VARCHAR(100),
            iris_ref       VARCHAR(100),
            filed_at       TIMESTAMP,
            accepted_at    TIMESTAMP,
            pdf_s3         VARCHAR(512),
            status         VARCHAR(20)  NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','submitted','acknowledged','queried','accepted','rejected')),
            filed_by       BIGINT       REFERENCES admin_users(id) ON DELETE SET NULL,
            created_at     TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)

    # =========================================================================
    # DOMAIN M — System & Integration
    # =========================================================================

    # MED-M01: third_party_service_configs
    # Structured per-integration config for the admin Integration Management panel.
    op.execute("""
        CREATE TABLE IF NOT EXISTS third_party_service_configs (
            id                   SERIAL        PRIMARY KEY,
            service_code         VARCHAR(30)   NOT NULL UNIQUE,
            service_name         VARCHAR(100)  NOT NULL,
            service_category     VARCHAR(30)   NOT NULL
                CHECK (service_category IN (
                    'kyc','payment_gateway','vcn_issuer','scraping',
                    'delivery','notification','credit_bureau','llm'
                )),
            environment          VARCHAR(10)   NOT NULL DEFAULT 'production'
                CHECK (environment IN ('sandbox','production')),
            api_endpoint         VARCHAR(512),
            api_key_secret_ref   VARCHAR(100),
            webhook_url          VARCHAR(512),
            is_active            BOOLEAN       NOT NULL DEFAULT TRUE,
            health_check_url     VARCHAR(512),
            last_health_check_at TIMESTAMP,
            last_health_status   VARCHAR(20),
            error_rate_threshold DECIMAL(4,3)  NOT NULL DEFAULT 0.02,
            notes                TEXT,
            updated_by           BIGINT        REFERENCES admin_users(id) ON DELETE SET NULL,
            updated_at           TIMESTAMP     NOT NULL DEFAULT NOW(),
            created_at           TIMESTAMP     NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        INSERT INTO third_party_service_configs
            (service_code, service_name, service_category, environment) VALUES
            ('nadra_verisys',  'NADRA Verisys',         'kyc',             'production'),
            ('shufti_pro',     'Shufti Pro',            'kyc',             'sandbox'),
            ('rye_api',        'Rye API v2',            'scraping',        'sandbox'),
            ('brightdata',     'BrightData Proxies',    'scraping',        'production'),
            ('stripe_issuing', 'Stripe Issuing',        'vcn_issuer',      'sandbox'),
            ('lithic',         'Lithic',                'vcn_issuer',      'sandbox'),
            ('safepay',        'Safepay',               'payment_gateway', 'sandbox'),
            ('jazzcash',       'JazzCash',              'payment_gateway', 'sandbox'),
            ('easypaisa',      'EasyPaisa',             'payment_gateway', 'sandbox'),
            ('raast',          'Raast SBP',             'payment_gateway', 'sandbox'),
            ('aftership',      'AfterShip',             'delivery',        'production'),
            ('tcs',            'TCS Courier',           'delivery',        'production'),
            ('sendgrid',       'SendGrid',              'notification',    'sandbox'),
            ('firebase_fcm',   'Firebase FCM',          'notification',    'production'),
            ('tasdeeq',        'TASDEEQ Credit Bureau', 'credit_bureau',   'sandbox'),
            ('groq_llm',       'Groq LLaMA-3-70B',      'llm',             'production')
        ON CONFLICT (service_code) DO NOTHING;
    """)

    # MED-M02: rate_limit_configs
    # Database-driven rate limiting configuration for admin configurability.
    op.execute("""
        CREATE TABLE IF NOT EXISTS rate_limit_configs (
            id             SERIAL        PRIMARY KEY,
            limit_key      VARCHAR(100)  NOT NULL UNIQUE,
            description    TEXT,
            max_requests   INTEGER       NOT NULL,
            window_seconds INTEGER       NOT NULL,
            applies_to     VARCHAR(30)   NOT NULL
                CHECK (applies_to IN ('user','ip','device','phone','global')),
            action         VARCHAR(20)   NOT NULL DEFAULT 'block'
                CHECK (action IN ('block','throttle','flag')),
            is_active      BOOLEAN       NOT NULL DEFAULT TRUE,
            updated_by     BIGINT        REFERENCES admin_users(id) ON DELETE SET NULL,
            updated_at     TIMESTAMP     NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        INSERT INTO rate_limit_configs
            (limit_key, description, max_requests, window_seconds, applies_to, action) VALUES
            ('otp_per_phone_hour',    'OTP requests per phone per hour',   3,  3600,  'phone',  'block'),
            ('login_per_ip_hour',     'Login attempts per IP per hour',    20, 3600,  'ip',     'block'),
            ('orders_per_user_day',   'Orders per user per 24h',           3,  86400, 'user',   'block'),
            ('orders_per_device_day', 'Orders per device per 24h',         3,  86400, 'device', 'block'),
            ('kyc_attempts_per_phone','KYC attempts per phone per hour',   3,  3600,  'phone',  'block'),
            ('api_per_key_minute',    'API calls per key per minute',      60, 60,    'user',   'throttle')
        ON CONFLICT (limit_key) DO NOTHING;
    """)

    # MED-M03: scheduled_task_runs
    # Run history for the admin System Health dashboard.
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_task_runs (
            id             BIGSERIAL    PRIMARY KEY,
            task_name      VARCHAR(100) NOT NULL REFERENCES scheduled_tasks(task_name) ON DELETE CASCADE,
            started_at     TIMESTAMP    NOT NULL,
            completed_at   TIMESTAMP,
            status         VARCHAR(20)  NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','success','failed')),
            rows_processed INTEGER,
            error_message  TEXT,
            duration_ms    INTEGER
                GENERATED ALWAYS AS (
                    EXTRACT(EPOCH FROM (completed_at - started_at))::INTEGER * 1000
                ) STORED
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_runs_name_started
            ON scheduled_task_runs (task_name, started_at DESC);
    """)


def downgrade() -> None:
    # Domain M
    op.execute("DROP TABLE IF EXISTS scheduled_task_runs CASCADE;")
    op.execute("DROP TABLE IF EXISTS rate_limit_configs CASCADE;")
    op.execute("DROP TABLE IF EXISTS third_party_service_configs CASCADE;")

    # Domain L
    op.execute("DROP TABLE IF EXISTS secp_filings CASCADE;")
    op.execute("DROP TABLE IF EXISTS pci_dss_assessments CASCADE;")
    op.execute("DROP TABLE IF EXISTS regulatory_calendar CASCADE;")

    # Domain J
    op.execute("DROP TABLE IF EXISTS campaign_segments CASCADE;")
    op.execute("DROP TABLE IF EXISTS user_segments CASCADE;")

    # Domain I
    op.execute("DROP TABLE IF EXISTS support_ticket_sla_configs CASCADE;")
    op.execute("DROP TABLE IF EXISTS chatbot_sessions CASCADE;")

    # Domain H
    op.execute("DROP TABLE IF EXISTS balance_sheet_snapshots CASCADE;")
    op.execute("DROP TABLE IF EXISTS tax_filings CASCADE;")

    # Domain G
    op.execute("DROP TABLE IF EXISTS charity_disbursements CASCADE;")
    op.execute("DROP TABLE IF EXISTS murabaha_contract_templates CASCADE;")

    # Domain F
    op.execute("DROP TABLE IF EXISTS delivery_sla_configs CASCADE;")
    op.execute("DROP TABLE IF EXISTS delivery_zones CASCADE;")

    # Domain E
    op.execute("DROP TABLE IF EXISTS write_off_records CASCADE;")
    op.execute("DROP TABLE IF EXISTS loan_loss_provisions CASCADE;")
    op.execute("DROP TABLE IF EXISTS payment_plan_configurations CASCADE;")

    # Domain A
    op.execute("DROP TABLE IF EXISTS cnic_division_codes CASCADE;")
    op.execute("DROP TABLE IF EXISTS pk_mobile_prefixes CASCADE;")
