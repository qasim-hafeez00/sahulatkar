-- ============================================================
-- Migration 041: Production Hardening
-- Run via: docker exec sk-postgres psql -U sk_admin -d sahulatkar -f /041.sql
-- ============================================================

BEGIN;

-- Record this migration in alembic_version
UPDATE alembic_version SET version_num = '041_production_hardening';

-- ═══════════════════════════════════════════════════════════════════════
-- CRIT-01: Fix UUID → BIGINT type mismatch
-- ═══════════════════════════════════════════════════════════════════════

-- credit_applications.user_id
ALTER TABLE credit_applications
    ALTER COLUMN user_id TYPE BIGINT USING user_id::text::bigint;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ca_user_id') THEN
        ALTER TABLE credit_applications
            ADD CONSTRAINT fk_ca_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
    END IF;
END $$;

-- risk_assessments: user_id, order_id, credit_app_id
ALTER TABLE risk_assessments
    ALTER COLUMN user_id TYPE BIGINT USING user_id::text::bigint;
ALTER TABLE risk_assessments
    ALTER COLUMN order_id TYPE BIGINT USING order_id::text::bigint;
ALTER TABLE risk_assessments
    ALTER COLUMN credit_app_id TYPE BIGINT USING credit_app_id::text::bigint;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ra_user_id') THEN
        ALTER TABLE risk_assessments
            ADD CONSTRAINT fk_ra_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
    END IF;
END $$;

-- velocity_checks.user_id
ALTER TABLE velocity_checks
    ALTER COLUMN user_id TYPE BIGINT USING user_id::text::bigint;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_vc_user_id') THEN
        ALTER TABLE velocity_checks
            ADD CONSTRAINT fk_vc_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
    END IF;
END $$;

-- credit_limit_history.user_id (conditional — may already be BIGINT)
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'credit_limit_history' AND column_name = 'user_id' AND data_type = 'uuid'
    ) THEN
        ALTER TABLE credit_limit_history ALTER COLUMN user_id TYPE BIGINT USING user_id::text::bigint;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_clh_user_id') THEN
        ALTER TABLE credit_limit_history
            ADD CONSTRAINT fk_clh_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- CRIT-02: installments — restore retry_count and next_retry_at
-- ═══════════════════════════════════════════════════════════════════════
ALTER TABLE installments
    ADD COLUMN IF NOT EXISTS retry_count   SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP;

-- ═══════════════════════════════════════════════════════════════════════
-- CRIT-03: loans — unique constraint on order_id (one Murabaha loan per order)
-- NOTE: A referential FK from loans.order_id → orders(id) is not possible
-- because orders is a partitioned table with a composite PK (id, created_at).
-- PostgreSQL requires all PK columns in a FK reference to a partitioned table.
-- The application-layer enforces the referential integrity at insert time.
-- The unique constraint below enforces the "one loan per order" business rule.
-- ═══════════════════════════════════════════════════════════════════════
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_loans_order_id') THEN
        ALTER TABLE loans ADD CONSTRAINT uq_loans_order_id UNIQUE (order_id);
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- CRIT-04: wakalah_agreements — add missing spec columns
-- ═══════════════════════════════════════════════════════════════════════
ALTER TABLE wakalah_agreements
    ADD COLUMN IF NOT EXISTS is_executed       BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS executed_at       TIMESTAMP,
    ADD COLUMN IF NOT EXISTS valid_from        TIMESTAMP,
    ADD COLUMN IF NOT EXISTS signing_ip        INET,
    ADD COLUMN IF NOT EXISTS signing_device_id BIGINT,
    ADD COLUMN IF NOT EXISTS signed_via        VARCHAR(20) NOT NULL DEFAULT 'otp';

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_wa_signed_via') THEN
        ALTER TABLE wakalah_agreements ADD CONSTRAINT chk_wa_signed_via
            CHECK (signed_via IN ('otp','biometric','digital_cert'));
    END IF;
END $$;

-- Backfill valid_until for any NULL rows before adding NOT NULL
UPDATE wakalah_agreements SET valid_until = created_at + INTERVAL '24 hours' WHERE valid_until IS NULL;
ALTER TABLE wakalah_agreements ALTER COLUMN valid_until SET NOT NULL;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_wa_signing_device') THEN
        ALTER TABLE wakalah_agreements ADD CONSTRAINT fk_wa_signing_device
            FOREIGN KEY (signing_device_id) REFERENCES user_devices(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- CRIT-05 + HIGH-05: murabaha_contracts — add columns + rename columns
-- ═══════════════════════════════════════════════════════════════════════
ALTER TABLE murabaha_contracts
    ADD COLUMN IF NOT EXISTS loan_id               BIGINT,
    ADD COLUMN IF NOT EXISTS product_specification TEXT,
    ADD COLUMN IF NOT EXISTS delivery_obligation   VARCHAR(100) NOT NULL DEFAULT 'merchant_to_customer',
    ADD COLUMN IF NOT EXISTS payment_plan          VARCHAR(20),
    ADD COLUMN IF NOT EXISTS contract_pdf_s3       VARCHAR(512),
    ADD COLUMN IF NOT EXISTS signed_via            VARCHAR(20) NOT NULL DEFAULT 'otp',
    ADD COLUMN IF NOT EXISTS signing_ip            INET,
    ADD COLUMN IF NOT EXISTS shariah_approval_ref  VARCHAR(50),
    ADD COLUMN IF NOT EXISTS status                VARCHAR(20) NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS completed_at          TIMESTAMP;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_mc_signed_via') THEN
        ALTER TABLE murabaha_contracts ADD CONSTRAINT chk_mc_signed_via
            CHECK (signed_via IN ('otp','biometric','digital_cert'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_mc_status') THEN
        ALTER TABLE murabaha_contracts ADD CONSTRAINT chk_mc_status
            CHECK (status IN ('active','completed','cancelled','disputed'));
    END IF;
END $$;

-- Rename total_sale_price → total_repayable
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'murabaha_contracts' AND column_name = 'total_sale_price'
    ) THEN
        ALTER TABLE murabaha_contracts RENAME COLUMN total_sale_price TO total_repayable;
    END IF;
END $$;

-- Rename wakalah_agreement_id → wakalah_id (drop old FK, rename, re-add FK)
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'murabaha_contracts_wakalah_agreement_id_fkey') THEN
        ALTER TABLE murabaha_contracts DROP CONSTRAINT murabaha_contracts_wakalah_agreement_id_fkey;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'murabaha_contracts' AND column_name = 'wakalah_agreement_id'
    ) THEN
        ALTER TABLE murabaha_contracts RENAME COLUMN wakalah_agreement_id TO wakalah_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_mc_wakalah_id') THEN
        ALTER TABLE murabaha_contracts ADD CONSTRAINT fk_mc_wakalah_id
            FOREIGN KEY (wakalah_id) REFERENCES wakalah_agreements(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_mc_loan_id') THEN
        ALTER TABLE murabaha_contracts ADD CONSTRAINT fk_mc_loan_id
            FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- CRIT-06: users — add phone_verified_at
-- ═══════════════════════════════════════════════════════════════════════
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP;

-- ═══════════════════════════════════════════════════════════════════════
-- CRIT-07: FKs to orders partitioned parent
-- NOTE: orders PK is (id, created_at) — a composite key. PostgreSQL requires
-- all partition PK columns in any FK reference. Since child tables
-- (referrals, support_tickets, etc.) store only order_id (not created_at),
-- these FKs cannot be declared at the DB level. Application-layer enforces
-- referential integrity. This is the same documented limitation as migrations
-- 032-040. No action taken here for orders-referencing FKs.
-- ═══════════════════════════════════════════════════════════════════════
SELECT 'CRIT-07: FK to partitioned orders not applicable — see comment above' AS note;

-- ═══════════════════════════════════════════════════════════════════════
-- HIGH-01: velocity_checks — add checked_at column
-- ═══════════════════════════════════════════════════════════════════════
ALTER TABLE velocity_checks ADD COLUMN IF NOT EXISTS checked_at TIMESTAMP NOT NULL DEFAULT NOW();
UPDATE velocity_checks SET checked_at = updated_at WHERE checked_at > NOW() - INTERVAL '1 second';

CREATE INDEX IF NOT EXISTS idx_vc_user_type_checked
    ON velocity_checks(user_id, check_type, checked_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- HIGH-02: credit_applications — add missing columns + CHECK constraints
-- ═══════════════════════════════════════════════════════════════════════
ALTER TABLE credit_applications
    ADD COLUMN IF NOT EXISTS decided_at          TIMESTAMP,
    ADD COLUMN IF NOT EXISTS decided_by_admin_id BIGINT,
    ADD COLUMN IF NOT EXISTS processing_time_ms  INTEGER;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ca_decided_by') THEN
        ALTER TABLE credit_applications ADD CONSTRAINT chk_ca_decided_by
            CHECK (decided_by IN ('auto_engine','manual_admin') OR decided_by IS NULL);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ca_application_type') THEN
        ALTER TABLE credit_applications ADD CONSTRAINT chk_ca_application_type
            CHECK (application_type IN (
                'onboarding','limit_increase','limit_review','manual_request','periodic_review'
            ));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ca_decided_by_admin') THEN
        ALTER TABLE credit_applications ADD CONSTRAINT fk_ca_decided_by_admin
            FOREIGN KEY (decided_by_admin_id) REFERENCES admin_users(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- HIGH-04: risk_assessments — FK to credit_applications
-- NOTE: FK to orders(id) not possible — orders PK is composite (id, created_at).
--       Same limitation as CRIT-03/CRIT-07. Application-layer enforces integrity.
-- ═══════════════════════════════════════════════════════════════════════
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ra_credit_app') THEN
        ALTER TABLE risk_assessments ADD CONSTRAINT fk_ra_credit_app
            FOREIGN KEY (credit_app_id) REFERENCES credit_applications(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- HIGH-06: Reapply audit triggers on recreated tables
-- ═══════════════════════════════════════════════════════════════════════
DO $$ DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['loans','installments','orders','payment_transactions'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_audit_%s ON %I', t, t);
        EXECUTE format(
            'CREATE TRIGGER trg_audit_%s AFTER INSERT OR UPDATE OR DELETE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION fn_log_audit()', t, t
        );
    END LOOP;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- MED-01: users — CHECK constraints
-- ═══════════════════════════════════════════════════════════════════════
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_status') THEN
        ALTER TABLE users ADD CONSTRAINT chk_users_status
            CHECK (status IN ('pending_kyc','active','suspended','closed','blocked'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_kyc_status') THEN
        ALTER TABLE users ADD CONSTRAINT chk_users_kyc_status
            CHECK (kyc_status IN ('pending','in_review','verified','rejected','expired'));
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
            CHECK (province IN ('Sindh','Punjab','KPK','Balochistan','Gilgit-Baltistan','AJK','ICT') OR province IS NULL);
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- MED-02: loans — CHECK constraints
-- ═══════════════════════════════════════════════════════════════════════
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_loans_status') THEN
        ALTER TABLE loans ADD CONSTRAINT chk_loans_status
            CHECK (status IN ('active','partially_paid','fully_paid','defaulted','written_off','disputed'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_loans_plan_type') THEN
        ALTER TABLE loans ADD CONSTRAINT chk_loans_plan_type
            CHECK (plan_type IN ('pay_in_3','pay_in_4','pay_in_6','pay_full'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_loans_installment_count') THEN
        ALTER TABLE loans ADD CONSTRAINT chk_loans_installment_count
            CHECK (installment_count BETWEEN 1 AND 6);
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- MED-03: installments — CHECK on status
-- ═══════════════════════════════════════════════════════════════════════
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_installments_status') THEN
        ALTER TABLE installments ADD CONSTRAINT chk_installments_status
            CHECK (status IN ('pending','paid','overdue','defaulted','waived','rescheduled'));
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- MED-04: payment_transactions — CHECK on gateway + status
-- ═══════════════════════════════════════════════════════════════════════
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ptxn_gateway') THEN
        ALTER TABLE payment_transactions ADD CONSTRAINT chk_ptxn_gateway
            CHECK (gateway IN ('safepay','jazzcash','easypaisa','raast','stripe','manual'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ptxn_status') THEN
        ALTER TABLE payment_transactions ADD CONSTRAINT chk_ptxn_status
            CHECK (status IN ('initiated','pending','success','failed','refunded','partially_refunded','chargeback'));
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- MED-05: fn_set_updated_at() triggers on 11 tables
-- ═══════════════════════════════════════════════════════════════════════
DO $$ DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'credit_applications','risk_assessments','merchants','products',
        'virtual_cards','wakalah_agreements','murabaha_contracts',
        'support_tickets','promotional_codes','admin_users','user_kyc_verifications'
    ] LOOP
        BEGIN
            EXECUTE format(
                'DROP TRIGGER IF EXISTS trg_%s_updated_at ON %I;
                 CREATE TRIGGER trg_%s_updated_at BEFORE UPDATE ON %I
                 FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at()',
                t, t, t, t
            );
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Skipped updated_at trigger for %: %', t, SQLERRM;
        END;
    END LOOP;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- MED-06: Covering index for credit check (Volume II §17.2)
-- ═══════════════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_users_credit_check
    ON users(id) INCLUDE (credit_limit, available_credit, status, risk_level)
    WHERE deleted_at IS NULL;

-- ═══════════════════════════════════════════════════════════════════════
-- MED-07: Partial index for vcn_issued queue (Volume II §17.2 QP4)
-- ═══════════════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_orders_vcn_issued
    ON orders(created_at ASC)
    WHERE status = 'vcn_issued';

-- ═══════════════════════════════════════════════════════════════════════
-- MED-08: Partial index for active virtual cards
-- ═══════════════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_vcn_status_active
    ON virtual_cards(status)
    WHERE status = 'active';

-- ═══════════════════════════════════════════════════════════════════════
-- MED-09: scraping_jobs — ensure order_id column exists
-- NOTE: FK from scraping_jobs.order_id → orders(id) is not possible because
--       orders is partitioned with composite PK (id, created_at).
--       Application-layer enforces referential integrity.
-- ═══════════════════════════════════════════════════════════════════════
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'scraping_jobs' AND column_name = 'order_id'
    ) THEN
        ALTER TABLE scraping_jobs ADD COLUMN order_id BIGINT;
    END IF;
END $$;

-- Add a supporting index for scraping_jobs.order_id lookups
CREATE INDEX IF NOT EXISTS idx_scraping_jobs_order_id ON scraping_jobs(order_id) WHERE order_id IS NOT NULL;

COMMIT;
