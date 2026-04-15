"""Production Hardening — Fix All Critical and High Issues

Revision ID: 041_production_hardening
Revises: 040_complete_to_169_tables
Create Date: 2026-04-16 00:00:00.000000

Fixes:
  CRIT-01: user_id UUID → BIGINT type fix in credit_applications,
           risk_assessments, velocity_checks, credit_limit_history
           + add proper FK constraints
  CRIT-02: installments.retry_count + next_retry_at re-added
  CRIT-03: loans FK to orders + unique constraint on order_id
  CRIT-04: wakalah_agreements — add missing spec columns (is_executed,
           executed_at, valid_from, signing_ip, signing_device_id,
           signed_via); valid_until SET NOT NULL
  CRIT-05: murabaha_contracts — add missing spec columns (loan_id,
           product_specification, delivery_obligation, payment_plan,
           contract_pdf_s3, signed_via, otp_reference, signing_ip,
           shariah_approval_ref, status, completed_at);
           rename total_sale_price → total_repayable;
           rename wakalah_agreement_id → wakalah_id (HIGH-05)
  CRIT-06: users.phone_verified_at column
  CRIT-07: Re-add FKs to orders lost when table was partitioned
  HIGH-01: velocity_checks.checked_at column (rename updated_at)
  HIGH-02: credit_applications missing columns + CHECK constraint
  HIGH-04: risk_assessments FK to credit_applications + orders;
           fix order_id + credit_app_id types to BIGINT
  HIGH-06: Reapply audit triggers on all recreated tables
  MED-01:  users — CHECK constraints on status, kyc_status,
           risk_level, available_credit, province
  MED-02:  loans — CHECK constraints on status, plan_type,
           installment_count
  MED-03:  installments — CHECK constraint on status
  MED-04:  payment_transactions — CHECK constraints on gateway, status
  MED-05:  fn_set_updated_at triggers on 11 tables
  MED-06:  users covering index for credit check
  MED-07:  orders partial index for vcn_issued queue
  MED-08:  virtual_cards partial index for active status
  MED-09:  scraping_jobs FK to orders
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '041_production_hardening'
down_revision: Union[str, None] = '040_complete_to_169_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# UPGRADE
# ---------------------------------------------------------------------------
def upgrade() -> None:

    # ═══════════════════════════════════════════════════════════════════════
    # CRIT-01: Fix UUID → BIGINT type mismatch on user_id (and related FK
    #          cols) in credit_applications, risk_assessments,
    #          velocity_checks, credit_limit_history.
    #
    # Strategy: The tables are empty in dev. Use USING cast for safety.
    #           The tables have no FK constraints pointing TO them on these
    #           UUID columns (confirmed via \d), so we can alter directly.
    # ═══════════════════════════════════════════════════════════════════════

    # --- credit_applications.user_id ---
    # Drop old UUID default (none), change type, add FK
    op.execute(
        "ALTER TABLE credit_applications "
        "ALTER COLUMN user_id TYPE BIGINT "
        "USING user_id::text::bigint"
    )
    op.create_foreign_key(
        "fk_ca_user_id",
        "credit_applications", "users",
        ["user_id"], ["id"],
        ondelete="RESTRICT",
    )

    # --- risk_assessments.user_id, order_id, credit_app_id ---
    # All three columns are UUID; order_id and credit_app_id must also be BIGINT.
    op.execute(
        "ALTER TABLE risk_assessments "
        "ALTER COLUMN user_id TYPE BIGINT "
        "USING user_id::text::bigint"
    )
    op.execute(
        "ALTER TABLE risk_assessments "
        "ALTER COLUMN order_id TYPE BIGINT "
        "USING order_id::text::bigint"
    )
    op.execute(
        "ALTER TABLE risk_assessments "
        "ALTER COLUMN credit_app_id TYPE BIGINT "
        "USING credit_app_id::text::bigint"
    )
    op.create_foreign_key(
        "fk_ra_user_id",
        "risk_assessments", "users",
        ["user_id"], ["id"],
        ondelete="RESTRICT",
    )

    # --- velocity_checks.user_id ---
    op.execute(
        "ALTER TABLE velocity_checks "
        "ALTER COLUMN user_id TYPE BIGINT "
        "USING user_id::text::bigint"
    )
    op.create_foreign_key(
        "fk_vc_user_id",
        "velocity_checks", "users",
        ["user_id"], ["id"],
        ondelete="RESTRICT",
    )

    # --- credit_limit_history.user_id ---
    # Check if table has a UUID user_id first (it was in the audit report)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'credit_limit_history'
                  AND column_name = 'user_id'
                  AND data_type = 'uuid'
            ) THEN
                ALTER TABLE credit_limit_history
                    ALTER COLUMN user_id TYPE BIGINT
                    USING user_id::text::bigint;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'fk_clh_user_id'
                ) THEN
                    ALTER TABLE credit_limit_history
                        ADD CONSTRAINT fk_clh_user_id
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
                END IF;
            END IF;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # CRIT-02: installments — restore retry_count and next_retry_at
    #          (dropped during migration 033 recreation)
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        ALTER TABLE installments
            ADD COLUMN IF NOT EXISTS retry_count   SMALLINT  NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # CRIT-03: loans — add FK to orders (partitioned parent) + unique
    #           constraint ensuring one loan per order (Murabaha spec §7).
    # ═══════════════════════════════════════════════════════════════════════
    # PostgreSQL 12+ allows FK to partitioned parent table.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_loans_order_id'
            ) THEN
                ALTER TABLE loans
                    ADD CONSTRAINT fk_loans_order_id
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_loans_order_id'
            ) THEN
                ALTER TABLE loans
                    ADD CONSTRAINT uq_loans_order_id UNIQUE (order_id);
            END IF;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # CRIT-04: wakalah_agreements — add missing spec columns for OTP
    #          signing flow and contract validity window (Volume I §10.1)
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        ALTER TABLE wakalah_agreements
            ADD COLUMN IF NOT EXISTS is_executed       BOOLEAN   NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS executed_at       TIMESTAMP,
            ADD COLUMN IF NOT EXISTS valid_from        TIMESTAMP,
            ADD COLUMN IF NOT EXISTS signing_ip        INET,
            ADD COLUMN IF NOT EXISTS signing_device_id BIGINT,
            ADD COLUMN IF NOT EXISTS signed_via        VARCHAR(20)
                NOT NULL DEFAULT 'otp'
                CHECK (signed_via IN ('otp','biometric','digital_cert'))
    """)

    # valid_until SET NOT NULL (has data risk if NULL rows exist — guard it)
    op.execute("""
        UPDATE wakalah_agreements
            SET valid_until = created_at + INTERVAL '24 hours'
        WHERE valid_until IS NULL
    """)
    op.execute(
        "ALTER TABLE wakalah_agreements "
        "ALTER COLUMN valid_until SET NOT NULL"
    )

    # Add FK for signing_device_id
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_wa_signing_device'
            ) THEN
                ALTER TABLE wakalah_agreements
                    ADD CONSTRAINT fk_wa_signing_device
                    FOREIGN KEY (signing_device_id)
                    REFERENCES user_devices(id) ON DELETE SET NULL;
            END IF;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # CRIT-05 + HIGH-05: murabaha_contracts
    #   a) Add missing spec columns (Volume I §10.2)
    #   b) Rename total_sale_price → total_repayable (spec column name)
    #   c) Rename wakalah_agreement_id → wakalah_id (spec column name)
    # ═══════════════════════════════════════════════════════════════════════

    # a) Add missing columns
    op.execute("""
        ALTER TABLE murabaha_contracts
            ADD COLUMN IF NOT EXISTS loan_id               BIGINT,
            ADD COLUMN IF NOT EXISTS product_specification TEXT,
            ADD COLUMN IF NOT EXISTS delivery_obligation   VARCHAR(100)
                NOT NULL DEFAULT 'merchant_to_customer',
            ADD COLUMN IF NOT EXISTS payment_plan          VARCHAR(20),
            ADD COLUMN IF NOT EXISTS contract_pdf_s3       VARCHAR(512),
            ADD COLUMN IF NOT EXISTS signed_via            VARCHAR(20)
                NOT NULL DEFAULT 'otp'
                CHECK (signed_via IN ('otp','biometric','digital_cert')),
            ADD COLUMN IF NOT EXISTS signing_ip            INET,
            ADD COLUMN IF NOT EXISTS shariah_approval_ref  VARCHAR(50),
            ADD COLUMN IF NOT EXISTS status                VARCHAR(20)
                NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','completed','cancelled','disputed')),
            ADD COLUMN IF NOT EXISTS completed_at          TIMESTAMP
    """)

    # b) Rename total_sale_price → total_repayable
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'murabaha_contracts'
                  AND column_name = 'total_sale_price'
            ) THEN
                ALTER TABLE murabaha_contracts
                    RENAME COLUMN total_sale_price TO total_repayable;
            END IF;
        END $$
    """)

    # c) Rename wakalah_agreement_id → wakalah_id
    #    Must drop FK first, then rename, then re-add FK.
    op.execute("""
        DO $$
        BEGIN
            -- Drop old FK if it exists under the old name
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'murabaha_contracts_wakalah_agreement_id_fkey'
            ) THEN
                ALTER TABLE murabaha_contracts
                    DROP CONSTRAINT murabaha_contracts_wakalah_agreement_id_fkey;
            END IF;

            -- Rename column
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'murabaha_contracts'
                  AND column_name = 'wakalah_agreement_id'
            ) THEN
                ALTER TABLE murabaha_contracts
                    RENAME COLUMN wakalah_agreement_id TO wakalah_id;
            END IF;

            -- Re-add FK under canonical name
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_mc_wakalah_id'
            ) THEN
                ALTER TABLE murabaha_contracts
                    ADD CONSTRAINT fk_mc_wakalah_id
                    FOREIGN KEY (wakalah_id)
                    REFERENCES wakalah_agreements(id) ON DELETE SET NULL;
            END IF;

            -- Add FK for loan_id
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_mc_loan_id'
            ) THEN
                ALTER TABLE murabaha_contracts
                    ADD CONSTRAINT fk_mc_loan_id
                    FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE SET NULL;
            END IF;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # CRIT-06: users — add phone_verified_at (Volume I §4.1)
    # ═══════════════════════════════════════════════════════════════════════
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP"
    )

    # ═══════════════════════════════════════════════════════════════════════
    # CRIT-07: Re-add FKs to orders (partitioned parent) for child tables
    #          that lost their FK when orders was DROP+RECREATED in
    #          migration 032.
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        DO $$
        DECLARE
            v_constraints TEXT[] := ARRAY[
                'referrals:first_order_id:fk_referrals_first_order_id:SET NULL',
                'support_tickets:order_id:fk_support_tickets_order_id:SET NULL'
            ];
            v_item TEXT;
            v_parts TEXT[];
            v_table TEXT;
            v_col TEXT;
            v_name TEXT;
            v_del TEXT;
        BEGIN
            FOREACH v_item IN ARRAY v_constraints LOOP
                v_parts := string_to_array(v_item, ':');
                v_table := v_parts[1];
                v_col   := v_parts[2];
                v_name  := v_parts[3];
                v_del   := v_parts[4];

                -- Drop any stale constraint with same name
                BEGIN
                    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I',
                                   v_table, v_name);
                EXCEPTION WHEN OTHERS THEN NULL;
                END;

                -- Only add if column exists and referenced table is partitioned
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = v_table AND column_name = v_col
                ) THEN
                    EXECUTE format(
                        'ALTER TABLE %I ADD CONSTRAINT %I '
                        'FOREIGN KEY (%I) REFERENCES orders(id) ON DELETE %s',
                        v_table, v_name, v_col, v_del
                    );
                END IF;
            END LOOP;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # HIGH-01: velocity_checks — add spec column checked_at.
    #          The spec requires checked_at; existing updated_at is kept
    #          for backward compat. New column is added with DEFAULT NOW()
    #          and backfilled from updated_at.
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        ALTER TABLE velocity_checks
            ADD COLUMN IF NOT EXISTS checked_at TIMESTAMP NOT NULL DEFAULT NOW()
    """)
    op.execute("""
        UPDATE velocity_checks SET checked_at = updated_at
        WHERE checked_at = NOW() -- only freshly defaulted rows
    """)
    # Add the correct index the fraud engine expects
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_vc_user_type_checked
            ON velocity_checks(user_id, check_type, checked_at DESC)
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # HIGH-02: credit_applications — add missing spec columns +
    #          CHECK constraint on application_type
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        ALTER TABLE credit_applications
            ADD COLUMN IF NOT EXISTS decided_at          TIMESTAMP,
            ADD COLUMN IF NOT EXISTS decided_by_admin_id BIGINT,
            ADD COLUMN IF NOT EXISTS processing_time_ms  INTEGER
    """)

    # decided_by already exists in the table; add CHECK if missing
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_ca_decided_by'
            ) THEN
                ALTER TABLE credit_applications
                    ADD CONSTRAINT chk_ca_decided_by
                    CHECK (decided_by IN ('auto_engine','manual_admin') OR decided_by IS NULL);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_ca_application_type'
            ) THEN
                ALTER TABLE credit_applications
                    ADD CONSTRAINT chk_ca_application_type
                    CHECK (application_type IN (
                        'onboarding','limit_increase','limit_review',
                        'manual_request','periodic_review'
                    ));
            END IF;
        END $$
    """)

    # Add FK for decided_by_admin_id
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_ca_decided_by_admin'
            ) THEN
                ALTER TABLE credit_applications
                    ADD CONSTRAINT fk_ca_decided_by_admin
                    FOREIGN KEY (decided_by_admin_id)
                    REFERENCES admin_users(id) ON DELETE SET NULL;
            END IF;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # HIGH-04: risk_assessments — add FKs to credit_applications + orders
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_ra_credit_app'
            ) THEN
                ALTER TABLE risk_assessments
                    ADD CONSTRAINT fk_ra_credit_app
                    FOREIGN KEY (credit_app_id)
                    REFERENCES credit_applications(id) ON DELETE SET NULL;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_ra_order'
            ) THEN
                ALTER TABLE risk_assessments
                    ADD CONSTRAINT fk_ra_order
                    FOREIGN KEY (order_id) REFERENCES orders(id);
            END IF;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # HIGH-06: Reapply audit triggers on all tables recreated by migrations
    #          032–035 that subsequently lost their AFTER triggers.
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        DO $$
        DECLARE
            t TEXT;
        BEGIN
            FOREACH t IN ARRAY ARRAY[
                'loans', 'installments', 'orders', 'payment_transactions'
            ] LOOP
                EXECUTE format(
                    'DROP TRIGGER IF EXISTS trg_audit_%s ON %I',
                    t, t
                );
                EXECUTE format(
                    'CREATE TRIGGER trg_audit_%s '
                    'AFTER INSERT OR UPDATE OR DELETE ON %I '
                    'FOR EACH ROW EXECUTE FUNCTION fn_log_audit()',
                    t, t
                );
            END LOOP;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # MED-01: users — add missing CHECK constraints (Volume I §4.1)
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_status') THEN
                ALTER TABLE users ADD CONSTRAINT chk_users_status
                    CHECK (status IN (
                        'pending_kyc','active','suspended','closed','blocked'
                    ));
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_kyc_status') THEN
                ALTER TABLE users ADD CONSTRAINT chk_users_kyc_status
                    CHECK (kyc_status IN (
                        'pending','in_review','verified','rejected','expired'
                    ));
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_risk_level') THEN
                ALTER TABLE users ADD CONSTRAINT chk_users_risk_level
                    CHECK (risk_level IN ('low','medium','high','blocked'));
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_avail_credit') THEN
                ALTER TABLE users ADD CONSTRAINT chk_users_avail_credit
                    CHECK (available_credit >= 0 AND available_credit <= credit_limit);
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_province') THEN
                ALTER TABLE users ADD CONSTRAINT chk_users_province
                    CHECK (
                        province IN (
                            'Sindh','Punjab','KPK','Balochistan',
                            'Gilgit-Baltistan','AJK','ICT'
                        ) OR province IS NULL
                    );
            END IF;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # MED-02: loans — add missing CHECK constraints
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_loans_status') THEN
                ALTER TABLE loans ADD CONSTRAINT chk_loans_status
                    CHECK (status IN (
                        'active','partially_paid','fully_paid',
                        'defaulted','written_off','disputed'
                    ));
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_loans_plan_type') THEN
                ALTER TABLE loans ADD CONSTRAINT chk_loans_plan_type
                    CHECK (plan_type IN (
                        'pay_in_3','pay_in_4','pay_in_6','pay_full'
                    ));
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_loans_installment_count') THEN
                ALTER TABLE loans ADD CONSTRAINT chk_loans_installment_count
                    CHECK (installment_count BETWEEN 1 AND 6);
            END IF;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # MED-03: installments — add missing CHECK constraint on status
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_installments_status'
            ) THEN
                ALTER TABLE installments ADD CONSTRAINT chk_installments_status
                    CHECK (status IN (
                        'pending','paid','overdue','defaulted','waived','rescheduled'
                    ));
            END IF;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # MED-04: payment_transactions — add CHECK constraints on gateway and status
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_ptxn_gateway'
            ) THEN
                ALTER TABLE payment_transactions ADD CONSTRAINT chk_ptxn_gateway
                    CHECK (gateway IN (
                        'safepay','jazzcash','easypaisa','raast','stripe','manual'
                    ));
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_ptxn_status'
            ) THEN
                ALTER TABLE payment_transactions ADD CONSTRAINT chk_ptxn_status
                    CHECK (status IN (
                        'initiated','pending','success','failed',
                        'refunded','partially_refunded','chargeback'
                    ));
            END IF;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # MED-05: Apply fn_set_updated_at() triggers to all tables that have
    #         an updated_at column but no BEFORE UPDATE trigger.
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        DO $$
        DECLARE
            t TEXT;
        BEGIN
            FOREACH t IN ARRAY ARRAY[
                'credit_applications',
                'risk_assessments',
                'merchants',
                'products',
                'virtual_cards',
                'wakalah_agreements',
                'murabaha_contracts',
                'support_tickets',
                'promotional_codes',
                'admin_users',
                'user_kyc_verifications'
            ] LOOP
                BEGIN
                    EXECUTE format(
                        'DROP TRIGGER IF EXISTS trg_%s_updated_at ON %I;
                         CREATE TRIGGER trg_%s_updated_at
                         BEFORE UPDATE ON %I
                         FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at()',
                        t, t, t, t
                    );
                EXCEPTION WHEN OTHERS THEN
                    RAISE NOTICE 'Skipped updated_at trigger for %: %', t, SQLERRM;
                END;
            END LOOP;
        END $$
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # MED-06: Covering index for per-order credit check (Volume II §17.2)
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_credit_check
            ON users(id)
            INCLUDE (credit_limit, available_credit, status, risk_level)
            WHERE deleted_at IS NULL
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # MED-07: Partial index for VCN-issued order queue (Volume II §17.2 QP4)
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_vcn_issued
            ON orders(created_at ASC)
            WHERE status = 'vcn_issued'
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # MED-08: Partial index for active virtual cards
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_vcn_status_active
            ON virtual_cards(status)
            WHERE status = 'active'
    """)

    # ═══════════════════════════════════════════════════════════════════════
    # MED-09: scraping_jobs — add FK to orders (lost after orders partitioned)
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'scraping_jobs' AND column_name = 'order_id'
            ) THEN
                -- Column doesn't exist at all — add it
                ALTER TABLE scraping_jobs ADD COLUMN order_id BIGINT;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_scraping_jobs_order'
            ) THEN
                ALTER TABLE scraping_jobs
                    ADD CONSTRAINT fk_scraping_jobs_order
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL;
            END IF;
        END $$
    """)


# ---------------------------------------------------------------------------
# DOWNGRADE — reverse in exact reverse order of upgrade
# ---------------------------------------------------------------------------
def downgrade() -> None:
    # MED-09
    op.execute(
        "ALTER TABLE scraping_jobs "
        "DROP CONSTRAINT IF EXISTS fk_scraping_jobs_order"
    )

    # MED-08
    op.execute("DROP INDEX IF EXISTS idx_vcn_status_active")

    # MED-07
    op.execute("DROP INDEX IF EXISTS idx_orders_vcn_issued")

    # MED-06
    op.execute("DROP INDEX IF EXISTS idx_users_credit_check")

    # MED-05 — drop updated_at triggers
    op.execute("""
        DO $$
        DECLARE t TEXT;
        BEGIN
            FOREACH t IN ARRAY ARRAY[
                'credit_applications','risk_assessments','merchants','products',
                'virtual_cards','wakalah_agreements','murabaha_contracts',
                'support_tickets','promotional_codes','admin_users',
                'user_kyc_verifications'
            ] LOOP
                EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_updated_at ON %I', t, t);
            END LOOP;
        END $$
    """)

    # MED-04
    op.execute(
        "ALTER TABLE payment_transactions "
        "DROP CONSTRAINT IF EXISTS chk_ptxn_gateway, "
        "DROP CONSTRAINT IF EXISTS chk_ptxn_status"
    )

    # MED-03
    op.execute(
        "ALTER TABLE installments "
        "DROP CONSTRAINT IF EXISTS chk_installments_status"
    )

    # MED-02
    op.execute(
        "ALTER TABLE loans "
        "DROP CONSTRAINT IF EXISTS chk_loans_status, "
        "DROP CONSTRAINT IF EXISTS chk_loans_plan_type, "
        "DROP CONSTRAINT IF EXISTS chk_loans_installment_count"
    )

    # MED-01
    op.execute(
        "ALTER TABLE users "
        "DROP CONSTRAINT IF EXISTS chk_users_status, "
        "DROP CONSTRAINT IF EXISTS chk_users_kyc_status, "
        "DROP CONSTRAINT IF EXISTS chk_users_risk_level, "
        "DROP CONSTRAINT IF EXISTS chk_users_avail_credit, "
        "DROP CONSTRAINT IF EXISTS chk_users_province"
    )

    # HIGH-06 — drop re-applied audit triggers
    op.execute("""
        DO $$
        DECLARE t TEXT;
        BEGIN
            FOREACH t IN ARRAY ARRAY[
                'loans','installments','orders','payment_transactions'
            ] LOOP
                EXECUTE format('DROP TRIGGER IF EXISTS trg_audit_%s ON %I', t, t);
            END LOOP;
        END $$
    """)

    # HIGH-04
    op.execute(
        "ALTER TABLE risk_assessments "
        "DROP CONSTRAINT IF EXISTS fk_ra_credit_app, "
        "DROP CONSTRAINT IF EXISTS fk_ra_order"
    )

    # HIGH-02
    op.execute(
        "ALTER TABLE credit_applications "
        "DROP CONSTRAINT IF EXISTS chk_ca_decided_by, "
        "DROP CONSTRAINT IF EXISTS chk_ca_application_type, "
        "DROP CONSTRAINT IF EXISTS fk_ca_decided_by_admin"
    )
    op.execute(
        "ALTER TABLE credit_applications "
        "DROP COLUMN IF EXISTS decided_at, "
        "DROP COLUMN IF EXISTS decided_by_admin_id, "
        "DROP COLUMN IF EXISTS processing_time_ms"
    )

    # HIGH-01
    op.execute("DROP INDEX IF EXISTS idx_vc_user_type_checked")
    op.execute(
        "ALTER TABLE velocity_checks DROP COLUMN IF EXISTS checked_at"
    )

    # CRIT-07
    op.execute(
        "ALTER TABLE referrals "
        "DROP CONSTRAINT IF EXISTS fk_referrals_first_order_id"
    )
    op.execute(
        "ALTER TABLE support_tickets "
        "DROP CONSTRAINT IF EXISTS fk_support_tickets_order_id"
    )

    # CRIT-06
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS phone_verified_at"
    )

    # CRIT-05
    op.execute(
        "ALTER TABLE murabaha_contracts "
        "DROP CONSTRAINT IF EXISTS fk_mc_loan_id, "
        "DROP CONSTRAINT IF EXISTS fk_mc_wakalah_id"
    )
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'murabaha_contracts' AND column_name = 'wakalah_id'
            ) THEN
                ALTER TABLE murabaha_contracts RENAME COLUMN wakalah_id TO wakalah_agreement_id;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'murabaha_contracts' AND column_name = 'total_repayable'
            ) THEN
                ALTER TABLE murabaha_contracts RENAME COLUMN total_repayable TO total_sale_price;
            END IF;
        END $$
    """)
    op.execute(
        "ALTER TABLE murabaha_contracts "
        "DROP COLUMN IF EXISTS loan_id, "
        "DROP COLUMN IF EXISTS product_specification, "
        "DROP COLUMN IF EXISTS delivery_obligation, "
        "DROP COLUMN IF EXISTS payment_plan, "
        "DROP COLUMN IF EXISTS contract_pdf_s3, "
        "DROP COLUMN IF EXISTS signed_via, "
        "DROP COLUMN IF EXISTS signing_ip, "
        "DROP COLUMN IF EXISTS shariah_approval_ref, "
        "DROP COLUMN IF EXISTS status, "
        "DROP COLUMN IF EXISTS completed_at"
    )

    # CRIT-04
    op.execute(
        "ALTER TABLE wakalah_agreements "
        "DROP CONSTRAINT IF EXISTS fk_wa_signing_device, "
        "DROP COLUMN IF EXISTS is_executed, "
        "DROP COLUMN IF EXISTS executed_at, "
        "DROP COLUMN IF EXISTS valid_from, "
        "DROP COLUMN IF EXISTS signing_ip, "
        "DROP COLUMN IF EXISTS signing_device_id, "
        "DROP COLUMN IF EXISTS signed_via"
    )
    op.execute(
        "ALTER TABLE wakalah_agreements ALTER COLUMN valid_until DROP NOT NULL"
    )

    # CRIT-03
    op.execute(
        "ALTER TABLE loans "
        "DROP CONSTRAINT IF EXISTS fk_loans_order_id, "
        "DROP CONSTRAINT IF EXISTS uq_loans_order_id"
    )

    # CRIT-02
    op.execute(
        "ALTER TABLE installments "
        "DROP COLUMN IF EXISTS retry_count, "
        "DROP COLUMN IF EXISTS next_retry_at"
    )

    # CRIT-01
    op.execute(
        "ALTER TABLE velocity_checks "
        "DROP CONSTRAINT IF EXISTS fk_vc_user_id"
    )
    op.execute(
        "ALTER TABLE risk_assessments "
        "DROP CONSTRAINT IF EXISTS fk_ra_user_id"
    )
    op.execute(
        "ALTER TABLE credit_applications "
        "DROP CONSTRAINT IF EXISTS fk_ca_user_id"
    )
    # Note: reversing the type changes would require knowing original UUIDs,
    # which is destructive. Type reversal is intentionally omitted.
