-- Lead The Way — Supabase / PostgreSQL schema
-- Run once in Supabase SQL Editor.  Safe to re-run (CREATE TABLE IF NOT EXISTS).
-- IMPORTANT: After running, disable RLS for all three tables in Supabase Dashboard
--            → Table Editor → Select table → Disable Row Level Security

-- ── Companies ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS target_companies (
    unique_id               VARCHAR(50)     PRIMARY KEY,
    company_name            VARCHAR(255)    NOT NULL,
    trade_name              VARCHAR(255),
    website                 VARCHAR(255),
    country                 VARCHAR(50),
    city                    VARCHAR(100),
    industry_code           VARCHAR(50),
    primary_activity        VARCHAR(500),
    employees_total         INTEGER,
    sales_volume_dollars    NUMERIC(20, 2),
    company_phone           VARCHAR(50),
    company_address         VARCHAR(500),
    company_state           VARCHAR(100),
    company_linkedin_url    VARCHAR(255),
    facebook_url            VARCHAR(255),
    twitter_url             VARCHAR(255),

    -- Intent layer (populated by Gemini grounding)
    intent_score            INTEGER         CHECK (intent_score BETWEEN 1 AND 10),
    intent_level            VARCHAR(20)     CHECK (intent_level IN ('LOW', 'MEDIUM', 'HIGH')),
    intent_signals          JSONB,
    grounding_urls          JSONB,
    last_intent_update      TIMESTAMP
);

-- ── People ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS people (
    person_id               BIGSERIAL       PRIMARY KEY,
    unique_id               VARCHAR(50)     REFERENCES target_companies(unique_id) ON DELETE SET NULL,
    first_name              VARCHAR(100),
    last_name               VARCHAR(100),
    title                   VARCHAR(255),
    email                   VARCHAR(255),
    phone                   VARCHAR(50),
    seniority               VARCHAR(100),
    department              VARCHAR(255),
    sub_department          VARCHAR(255),
    industry                VARCHAR(255),
    city                    VARCHAR(100),
    state                   VARCHAR(100),
    country                 VARCHAR(100),
    linkedin_url            VARCHAR(255),
    company_name            VARCHAR(255),
    company_city            VARCHAR(100),
    company_state           VARCHAR(100),
    company_country         VARCHAR(100),
    company_phone           VARCHAR(50),
    company_address         VARCHAR(500),
    company_linkedin_url    VARCHAR(255),
    facebook_url            VARCHAR(255),
    twitter_url             VARCHAR(255),
    employees               VARCHAR(50),
    annual_revenue          VARCHAR(50),
    technologies            JSONB,
    keywords                JSONB,
    opt_out                 BOOLEAN         NOT NULL DEFAULT FALSE
);

-- ── Indexes ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_tc_intent_level   ON target_companies (intent_level);
CREATE INDEX IF NOT EXISTS idx_tc_country        ON target_companies (country);
CREATE INDEX IF NOT EXISTS idx_tc_intent_score   ON target_companies (intent_score DESC);
CREATE INDEX IF NOT EXISTS idx_ppl_unique_id     ON people (unique_id);
CREATE INDEX IF NOT EXISTS idx_ppl_country       ON people (country);
CREATE INDEX IF NOT EXISTS idx_ppl_seniority     ON people (seniority);
CREATE INDEX IF NOT EXISTS idx_ppl_department    ON people (department);
CREATE INDEX IF NOT EXISTS idx_ppl_email         ON people (email);

-- ── KVKK Audit Log ──────────────────────────────────────────────────────────
-- Records every outreach-draft generation event for KVKK Article 12 accountability.
-- Retention: keep for 3 years; purge older rows with a scheduled job.
CREATE TABLE IF NOT EXISTS audit_log (
    id                  BIGSERIAL       PRIMARY KEY,
    event_time          TIMESTAMP       NOT NULL DEFAULT NOW(),
    event_type          VARCHAR(50)     NOT NULL,
    company_name        VARCHAR(255),
    person_email        VARCHAR(64),    -- SHA-256 prefix; raw PII never stored
    query_summary       TEXT,
    model_used          VARCHAR(100),
    pii_entities        JSONB,
    injection_flagged   BOOLEAN         NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_audit_event_time  ON audit_log (event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type  ON audit_log (event_type);
