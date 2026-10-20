-- Runs once on first Postgres container start (docker-entrypoint-initdb.d).
-- The database named by POSTGRES_DB already exists at this point.

-- Test database (pytest uses it).
SELECT 'CREATE DATABASE agent_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'agent_test') \gexec

-- pg_trgm is used for fuzzy citation/title matching.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- Application role
-- ---------------------------------------------------------------------------
-- RLS is bypassed entirely for superusers and (unless FORCE is set, which the
-- force_rls migration does) for table owners. The application must therefore
-- connect as a non-superuser role that owns nothing.
--
-- Password comes from the container env; default matches .env.example for dev
-- only. Override POSTGRES_APP_PASSWORD in production.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'compliance_app') THEN
        CREATE ROLE compliance_app LOGIN NOSUPERUSER NOBYPASSRLS
            PASSWORD 'compliance-app-dev';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE agent_dev TO compliance_app;
GRANT CONNECT ON DATABASE agent_test TO compliance_app;
GRANT USAGE ON SCHEMA public TO compliance_app;

-- DML on all current and future tables/sequences (migrations run as the owner).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO compliance_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO compliance_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO compliance_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO compliance_app;
