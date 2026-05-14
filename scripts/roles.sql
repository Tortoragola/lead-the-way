-- Lead The Way — role & permission setup (runs after schema.sql)
-- ltw_writer  : ETL scripts (INSERT / UPDATE / DELETE)
-- ltw_agent   : Gemini-driven agent paths (SELECT only — zero-trust)

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ltw_writer') THEN
    CREATE ROLE ltw_writer WITH LOGIN PASSWORD 'ltw_writer_secret' NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ltw_agent') THEN
    CREATE ROLE ltw_agent  WITH LOGIN PASSWORD 'ltw_agent_secret'  NOINHERIT;
  END IF;
END
$$;

-- Writer gets full DML on application tables
GRANT CONNECT ON DATABASE leadtheway TO ltw_writer;
GRANT USAGE ON SCHEMA public TO ltw_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON target_companies, people TO ltw_writer;

-- Agent gets read-only access only — no INSERT/UPDATE/DELETE ever
GRANT CONNECT ON DATABASE leadtheway TO ltw_agent;
GRANT USAGE ON SCHEMA public TO ltw_agent;
GRANT SELECT ON target_companies, people TO ltw_agent;
