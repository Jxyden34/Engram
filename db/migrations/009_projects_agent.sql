-- v2.7.0-dev-beta.1: project boundaries and review-only agent proposals.
CREATE TABLE IF NOT EXISTS projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,62}$'),
    name text NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120),
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO projects(id, slug, name)
VALUES ('00000000-0000-0000-0000-000000000001', 'personal', 'Personal')
ON CONFLICT (id) DO NOTHING;

CREATE OR REPLACE FUNCTION memorybank_current_project() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT COALESCE(NULLIF(current_setting('memorybank.project_id', true), '')::uuid,
                    '00000000-0000-0000-0000-000000000001'::uuid)
$$;

-- Older installations may have these import tables from manual upgrades;
-- bootstrap them for clean installations before applying project policies.
CREATE TABLE IF NOT EXISTS document_memory_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
    requested_by text NOT NULL,
    model_name text,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','failed')),
    chunk_count integer NOT NULL DEFAULT 0,
    processed_chunks integer NOT NULL DEFAULT 0,
    candidate_count integer NOT NULL DEFAULT 0,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS document_memory_jobs_document_idx ON document_memory_jobs(document_id, created_at DESC);

CREATE TABLE IF NOT EXISTS document_candidate_memories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES document_memory_jobs(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
    title text NOT NULL,
    content text NOT NULL,
    memory_type text NOT NULL DEFAULT 'general',
    importance smallint NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    confidence numeric(4,3) NOT NULL DEFAULT 0.8 CHECK (confidence BETWEEN 0 AND 1),
    tags text[] NOT NULL DEFAULT '{}',
    source_excerpt text,
    source_chunk_start integer,
    source_chunk_end integer,
    embedding vector(384),
    nearest_memory_id uuid REFERENCES memories(id),
    nearest_similarity numeric(6,5),
    comparison text CHECK (comparison IS NULL OR comparison IN ('new','duplicate','related','updates','conflicts')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected')),
    reviewed_by text,
    reviewed_at timestamptz,
    accepted_memory_id uuid REFERENCES memories(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS document_candidates_status_idx ON document_candidate_memories(status, created_at DESC);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'memories', 'memory_versions', 'memory_relations', 'deletion_requests',
        'documents', 'document_chunks', 'audit_log', 'chat_import_jobs', 'chat_import_conversations',
        'candidate_memories', 'entities', 'memory_entity_links', 'entity_relations',
        'events', 'event_entities', 'knowledge_enrichment', 'connectors',
        'connector_sync_runs', 'connector_items', 'browser_captures',
        'document_memory_jobs', 'document_candidate_memories'
    ] LOOP
        IF to_regclass('public.' || table_name) IS NULL THEN CONTINUE; END IF;
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS project_id uuid', table_name);
        EXECUTE format('UPDATE %I SET project_id = %L WHERE project_id IS NULL',
                       table_name, '00000000-0000-0000-0000-000000000001');
        EXECUTE format('ALTER TABLE %I ALTER COLUMN project_id SET DEFAULT memorybank_current_project()', table_name);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN project_id SET NOT NULL', table_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I(project_id)', table_name || '_project_idx', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS project_access ON %I', table_name);
        EXECUTE format('CREATE POLICY project_access ON %I USING (project_id = memorybank_current_project()) WITH CHECK (project_id = memorybank_current_project())', table_name);
    END LOOP;
END $$;

ALTER TABLE entities DROP CONSTRAINT IF EXISTS entities_normalized_name_entity_type_key;
CREATE UNIQUE INDEX IF NOT EXISTS entities_project_name_type_idx
    ON entities(project_id, normalized_name, entity_type);

-- A key stays in its selected project even if the caller supplies another header.
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id);
UPDATE api_keys SET project_id = '00000000-0000-0000-0000-000000000001' WHERE project_id IS NULL;
ALTER TABLE api_keys ALTER COLUMN project_id SET DEFAULT memorybank_current_project();
ALTER TABLE api_keys ALTER COLUMN project_id SET NOT NULL;

CREATE TABLE IF NOT EXISTS agent_proposals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL DEFAULT memorybank_current_project() REFERENCES projects(id),
    proposal_type text NOT NULL CHECK (proposal_type IN ('duplicate', 'conflict', 'stale', 'missing_provenance')),
    memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    related_memory_id uuid REFERENCES memories(id) ON DELETE CASCADE,
    reason text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'dismissed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz,
    reviewed_by text,
    UNIQUE NULLS NOT DISTINCT (project_id, proposal_type, memory_id, related_memory_id)
);
CREATE INDEX IF NOT EXISTS agent_proposals_pending_idx ON agent_proposals(project_id, status, created_at DESC);
ALTER TABLE agent_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_proposals FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_access ON agent_proposals;
CREATE POLICY project_access ON agent_proposals
    USING (project_id = memorybank_current_project())
    WITH CHECK (project_id = memorybank_current_project());

-- The bootstrap database user is a superuser in the official PostgreSQL image.
-- Application connections switch to this non-owner role so FORCE RLS applies.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='memorybank_runtime') THEN
        CREATE ROLE memorybank_runtime NOLOGIN;
    END IF;
    EXECUTE format('GRANT memorybank_runtime TO %I', current_user);
END $$;
GRANT USAGE ON SCHEMA public TO memorybank_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO memorybank_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO memorybank_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO memorybank_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO memorybank_runtime;
