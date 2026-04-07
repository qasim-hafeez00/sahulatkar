-- infra/docker/postgres/init.sql
-- Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- TimescaleDB loaded via base image

-- Database roles (mirrors production RDS roles)
CREATE ROLE sk_app LOGIN PASSWORD 'localdev123';
CREATE ROLE sk_app_readonly LOGIN PASSWORD 'localdev123';
CREATE ROLE sk_admin_api LOGIN PASSWORD 'localdev123';
CREATE ROLE sk_billing_worker LOGIN PASSWORD 'localdev123';
CREATE ROLE sk_reporting LOGIN PASSWORD 'localdev123';
CREATE ROLE sk_migrations LOGIN PASSWORD 'localdev123' SUPERUSER;

-- Grant schema access
GRANT ALL PRIVILEGES ON DATABASE sahulatkar TO sk_migrations;
GRANT CONNECT ON DATABASE sahulatkar TO sk_app, sk_app_readonly, sk_admin_api;

-- Shared utility functions
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fn_log_audit()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO audit_trails (
        table_name, record_id, action, old_data, new_data,
        actor_type, actor_id, changed_at
    ) VALUES (
        TG_TABLE_NAME,
        COALESCE(NEW.id, OLD.id),
        TG_OP,
        CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) END,
        CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) END,
        current_setting('app.actor_type', true),
        current_setting('app.actor_id', true)::BIGINT,
        NOW()
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
