CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_head (
    id smallint PRIMARY KEY CHECK (id = 1),
    seq bigint NOT NULL,
    hash text NOT NULL
);
INSERT INTO audit_head (id, seq, hash) VALUES (1, 0, repeat('0', 64)) ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS audit_events (
    seq bigint PRIMARY KEY,
    prev_hash text NOT NULL,
    hash text NOT NULL UNIQUE,
    event jsonb NOT NULL,
    ts timestamptz NOT NULL
);

CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only';
END;
$$ LANGUAGE plpgsql;

REVOKE ALL ON FUNCTION audit_events_immutable() FROM PUBLIC;

DROP TRIGGER IF EXISTS audit_events_no_mutation ON audit_events;
CREATE TRIGGER audit_events_no_mutation BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();

CREATE TABLE IF NOT EXISTS conversations (
    id text PRIMARY KEY,
    user_id text NOT NULL,
    persona text NOT NULL,
    title text NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    messages jsonb NOT NULL,
    sample boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS claims_log (
    id text PRIMARY KEY,
    policy_id text, customer_id text, event_type text, event_date text, admission_date text,
    discharge_date text, diagnosis_icd text, cause text, facility_id text, facility_is_bpjs_partner integer,
    is_emergency integer, billed_amount bigint, claim_amount bigint, status text, rejection_code text,
    filed_date text, deadline_date text, created_via text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_claims_log_customer ON claims_log (customer_id);

CREATE TABLE IF NOT EXISTS tickets_log (
    id text PRIMARY KEY,
    customer_id text, type text, status text, created_at text, payload_hash text,
    requested_via text, note text, session_id text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tickets_log_customer ON tickets_log (customer_id);

ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_head ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets_log ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE r text;
DECLARE t text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            FOREACH t IN ARRAY ARRAY['schema_migrations', 'audit_head', 'audit_events', 'conversations', 'claims_log', 'tickets_log'] LOOP
                EXECUTE format('REVOKE ALL ON TABLE %I FROM %I', t, r);
            END LOOP;
        END IF;
    END LOOP;
END $$;

INSERT INTO schema_migrations (version) VALUES ('001_init') ON CONFLICT (version) DO NOTHING;
