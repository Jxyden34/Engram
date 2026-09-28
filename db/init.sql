CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    display_name text,
    is_admin boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz
);

CREATE TABLE IF NOT EXISTS sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    csrf_hash text NOT NULL,
    ip_address inet,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS sessions_token_idx ON sessions(token_hash) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS api_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
    name text NOT NULL,
    key_prefix text NOT NULL,
    key_hash text NOT NULL UNIQUE,
    scopes text[] NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS api_keys_hash_idx ON api_keys(key_hash) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS memories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
    title text NOT NULL,
    content text NOT NULL,
    memory_type text NOT NULL DEFAULT 'general',
    importance smallint NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    confidence numeric(4,3) NOT NULL DEFAULT 1.000 CHECK (confidence BETWEEN 0 AND 1),
    tags text[] NOT NULL DEFAULT '{}',
    source_type text NOT NULL DEFAULT 'manual',
    source_ref text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by text NOT NULL,
    updated_by text NOT NULL,
    embedding vector(384),
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english'::regconfig, coalesce(title, '') || ' ' || coalesce(content, ''))
    ) STORED,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    deleted_by text
);
CREATE INDEX IF NOT EXISTS memories_embedding_hnsw_idx
    ON memories USING hnsw (embedding vector_cosine_ops)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS memories_search_idx ON memories USING gin(search_vector);
CREATE INDEX IF NOT EXISTS memories_type_idx ON memories(memory_type) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS memories_tags_idx ON memories USING gin(tags);
CREATE INDEX IF NOT EXISTS memories_updated_idx ON memories(updated_at DESC) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS memory_versions (
    id bigserial PRIMARY KEY,
    memory_id uuid NOT NULL REFERENCES memories(id),
    version_no integer NOT NULL,
    snapshot jsonb NOT NULL,
    actor text NOT NULL,
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(memory_id, version_no)
);

CREATE TABLE IF NOT EXISTS memory_relations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_memory_id uuid NOT NULL REFERENCES memories(id),
    to_memory_id uuid NOT NULL REFERENCES memories(id),
    relation_type text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(from_memory_id, to_memory_id, relation_type),
    CHECK (from_memory_id <> to_memory_id)
);
CREATE INDEX IF NOT EXISTS relation_from_idx ON memory_relations(from_memory_id);
CREATE INDEX IF NOT EXISTS relation_to_idx ON memory_relations(to_memory_id);

CREATE TABLE IF NOT EXISTS deletion_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id uuid NOT NULL REFERENCES memories(id),
    requested_by text NOT NULL,
    reason text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at timestamptz NOT NULL DEFAULT now(),
    reviewed_by text,
    reviewed_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_deletion_per_memory
    ON deletion_requests(memory_id) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
    filename text NOT NULL,
    object_key text NOT NULL UNIQUE,
    content_type text,
    byte_size bigint NOT NULL,
    sha256 text NOT NULL,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
    extraction_error text,
    uploaded_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    deleted_at timestamptz
);
CREATE INDEX IF NOT EXISTS documents_status_idx ON documents(status, created_at DESC);

CREATE TABLE IF NOT EXISTS document_chunks (
    id bigserial PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    embedding vector(384),
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english'::regconfig, coalesce(content, ''))
    ) STORED,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON document_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_search_idx ON document_chunks USING gin(search_vector);

CREATE TABLE IF NOT EXISTS audit_log (
    id bigserial PRIMARY KEY,
    actor text NOT NULL,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text,
    ip_address inet,
    reason text,
    old_data jsonb,
    new_data jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_created_idx ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS audit_entity_idx ON audit_log(entity_type, entity_id, created_at DESC);


-- ChatGPT import / candidate memory inbox
CREATE TABLE IF NOT EXISTS chat_import_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
    source_document_id uuid NOT NULL REFERENCES documents(id),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
    requested_by text NOT NULL,
    model_name text,
    conversation_count integer NOT NULL DEFAULT 0,
    processed_conversations integer NOT NULL DEFAULT 0,
    candidate_count integer NOT NULL DEFAULT 0,
    error_count integer NOT NULL DEFAULT 0,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS chat_import_jobs_created_idx
    ON chat_import_jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS chat_import_conversations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    import_job_id uuid NOT NULL REFERENCES chat_import_jobs(id) ON DELETE CASCADE,
    external_conversation_id text,
    title text NOT NULL,
    create_time timestamptz,
    update_time timestamptz,
    message_count integer NOT NULL DEFAULT 0,
    source_hash text NOT NULL,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(import_job_id, source_hash)
);

CREATE INDEX IF NOT EXISTS chat_import_conversation_job_idx
    ON chat_import_conversations(import_job_id, status);

CREATE TABLE IF NOT EXISTS candidate_memories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    import_job_id uuid NOT NULL REFERENCES chat_import_jobs(id) ON DELETE CASCADE,
    import_conversation_id uuid NOT NULL REFERENCES chat_import_conversations(id) ON DELETE CASCADE,
    owner_id uuid REFERENCES users(id) ON DELETE SET NULL,

    title text NOT NULL,
    content text NOT NULL,
    memory_type text NOT NULL DEFAULT 'general',
    importance smallint NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    confidence numeric(4,3) NOT NULL DEFAULT 0.800 CHECK (confidence BETWEEN 0 AND 1),
    tags text[] NOT NULL DEFAULT '{}',

    source_excerpt text,
    source_message_start timestamptz,
    source_message_end timestamptz,

    embedding vector(384),
    nearest_memory_id uuid REFERENCES memories(id),
    nearest_similarity numeric(6,5),
    comparison text
        CHECK (comparison IS NULL OR comparison IN ('new', 'duplicate', 'related', 'updates', 'conflicts')),

    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected')),
    reviewed_by text,
    reviewed_at timestamptz,
    accepted_memory_id uuid REFERENCES memories(id),

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS candidate_memories_job_status_idx
    ON candidate_memories(import_job_id, status, created_at);
CREATE INDEX IF NOT EXISTS candidate_memories_status_idx
    ON candidate_memories(status, created_at DESC);
CREATE INDEX IF NOT EXISTS candidate_memories_embedding_hnsw_idx
    ON candidate_memories USING hnsw (embedding vector_cosine_ops)
    WHERE status='pending';


-- Engram v2.0 Knowledge Core
-- Engram v2.0 Knowledge Core
ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_from timestamptz;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_to timestamptz;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS supersedes_memory_id uuid REFERENCES memories(id) ON DELETE SET NULL;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_trust numeric(4,3) NOT NULL DEFAULT 1.000 CHECK (source_trust BETWEEN 0 AND 1);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS access_count bigint NOT NULL DEFAULT 0;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS last_accessed_at timestamptz;
CREATE INDEX IF NOT EXISTS memories_validity_idx ON memories(valid_from, valid_to) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS memories_supersedes_idx ON memories(supersedes_memory_id) WHERE supersedes_memory_id IS NOT NULL;

UPDATE memories SET source_trust = CASE source_type
  WHEN 'manual' THEN 1.000
  WHEN 'chatgpt_import' THEN 0.920
  WHEN 'document_import' THEN 0.900
  ELSE LEAST(source_trust, 0.850)
END WHERE source_trust = 1.000;

CREATE TABLE IF NOT EXISTS entities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
  name text NOT NULL,
  normalized_name text NOT NULL,
  entity_type text NOT NULL DEFAULT 'other',
  description text,
  aliases text[] NOT NULL DEFAULT '{}',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding vector(384),
  created_by text NOT NULL,
  updated_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(normalized_name, entity_type)
);
CREATE INDEX IF NOT EXISTS entities_embedding_hnsw_idx ON entities USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS entities_type_idx ON entities(entity_type, updated_at DESC);

CREATE TABLE IF NOT EXISTS memory_entity_links (
  memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  role text NOT NULL DEFAULT 'mentions',
  confidence numeric(4,3) NOT NULL DEFAULT 1.000 CHECK (confidence BETWEEN 0 AND 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(memory_id, entity_id, role)
);
CREATE INDEX IF NOT EXISTS memory_entity_links_entity_idx ON memory_entity_links(entity_id, memory_id);

CREATE TABLE IF NOT EXISTS entity_relations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  to_entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  relation_type text NOT NULL,
  confidence numeric(4,3) NOT NULL DEFAULT 0.900 CHECK (confidence BETWEEN 0 AND 1),
  source_memory_id uuid REFERENCES memories(id) ON DELETE CASCADE,
  valid_from timestamptz,
  valid_to timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (from_entity_id <> to_entity_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS entity_relation_source_unique
  ON entity_relations(from_entity_id, to_entity_id, relation_type, source_memory_id)
  WHERE source_memory_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS entity_relations_from_idx ON entity_relations(from_entity_id);
CREATE INDEX IF NOT EXISTS entity_relations_to_idx ON entity_relations(to_entity_id);

CREATE TABLE IF NOT EXISTS events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
  title text NOT NULL,
  description text,
  event_type text NOT NULL DEFAULT 'event',
  occurred_at timestamptz,
  ended_at timestamptz,
  importance smallint NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
  confidence numeric(4,3) NOT NULL DEFAULT 0.900 CHECK (confidence BETWEEN 0 AND 1),
  source_type text NOT NULL DEFAULT 'memory',
  source_ref text,
  source_memory_id uuid REFERENCES memories(id) ON DELETE CASCADE,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding vector(384),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS events_source_memory_title_unique
  ON events(source_memory_id, lower(title), coalesce(occurred_at, '1970-01-01'::timestamptz))
  WHERE source_memory_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS events_time_idx ON events(occurred_at DESC NULLS LAST, created_at DESC);

CREATE TABLE IF NOT EXISTS event_entities (
  event_id uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  role text NOT NULL DEFAULT 'involved',
  PRIMARY KEY(event_id, entity_id, role)
);

CREATE TABLE IF NOT EXISTS knowledge_enrichment (
  memory_id uuid PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
  memory_updated_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','failed')),
  model_name text,
  entity_count integer NOT NULL DEFAULT 0,
  relation_count integer NOT NULL DEFAULT 0,
  event_count integer NOT NULL DEFAULT 0,
  error_message text,
  queued_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS knowledge_enrichment_status_idx ON knowledge_enrichment(status, queued_at);


-- v2.1 Ingestion Mesh

-- Engram v2.1 - Ingestion Mesh + Browser Capture

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS source_type text NOT NULL DEFAULT 'upload',
    ADD COLUMN IF NOT EXISTS source_ref text,
    ADD COLUMN IF NOT EXISTS source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS documents_source_idx
    ON documents(source_type, created_at DESC);

CREATE INDEX IF NOT EXISTS documents_source_ref_idx
    ON documents(source_ref)
    WHERE source_ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS connectors (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
    connector_type text NOT NULL,
    name text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    schedule_minutes integer NOT NULL DEFAULT 30
        CHECK (schedule_minutes BETWEEN 5 AND 10080),
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    cursor jsonb NOT NULL DEFAULT '{}'::jsonb,
    credential_ciphertext text,
    last_status text,
    last_error text,
    last_sync_at timestamptz,
    next_sync_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS connectors_due_idx
    ON connectors(enabled, next_sync_at)
    WHERE enabled=true;

CREATE TABLE IF NOT EXISTS connector_sync_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_id uuid NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','processing','ready','failed')),
    items_seen integer NOT NULL DEFAULT 0,
    items_changed integer NOT NULL DEFAULT 0,
    items_skipped integer NOT NULL DEFAULT 0,
    error_count integer NOT NULL DEFAULT 0,
    error_message text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS connector_runs_idx
    ON connector_sync_runs(connector_id, created_at DESC);

CREATE TABLE IF NOT EXISTS connector_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_id uuid NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    external_id text NOT NULL,
    item_type text NOT NULL,
    external_url text,
    title text,
    content_hash text NOT NULL,
    external_updated_at timestamptz,
    document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(connector_id, external_id)
);

CREATE INDEX IF NOT EXISTS connector_items_type_idx
    ON connector_items(connector_id, item_type, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS browser_captures (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    capture_type text NOT NULL
        CHECK (capture_type IN ('page','selection','link','note')),
    title text NOT NULL,
    url text,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS browser_captures_created_idx
    ON browser_captures(created_at DESC);


-- v2.2 OAuth / MCP Identity

-- Engram v2.2 - OAuth / MCP Identity

CREATE TABLE IF NOT EXISTS oauth_clients (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id text NOT NULL UNIQUE,
    client_name text NOT NULL,
    registration_type text NOT NULL
        CHECK (registration_type IN ('static','dynamic','cimd')),
    metadata_url text,
    redirect_uris text[] NOT NULL DEFAULT '{}',
    allowed_scopes text[] NOT NULL DEFAULT '{}',
    token_endpoint_auth_method text NOT NULL DEFAULT 'none',
    application_type text NOT NULL DEFAULT 'native',
    owner_id uuid REFERENCES users(id) ON DELETE SET NULL,
    created_by text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    last_used_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS oauth_clients_active_idx
    ON oauth_clients(is_active, created_at DESC);

CREATE TABLE IF NOT EXISTS oauth_consents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id text NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scopes text[] NOT NULL DEFAULT '{}',
    resource text NOT NULL,
    authorized_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at timestamptz,
    UNIQUE(client_id, user_id, resource)
);

CREATE INDEX IF NOT EXISTS oauth_consents_active_idx
    ON oauth_consents(user_id, revoked_at, authorized_at DESC);

CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code_hash text NOT NULL UNIQUE,
    client_id text NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    redirect_uri text NOT NULL,
    scopes text[] NOT NULL,
    resource text NOT NULL,
    code_challenge text NOT NULL,
    code_challenge_method text NOT NULL DEFAULT 'S256',
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS oauth_codes_lookup_idx
    ON oauth_authorization_codes(code_hash)
    WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash text NOT NULL UNIQUE,
    token_prefix text NOT NULL,
    family_id uuid NOT NULL,
    parent_id uuid REFERENCES oauth_refresh_tokens(id) ON DELETE SET NULL,
    client_id text NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scopes text[] NOT NULL,
    resource text NOT NULL,
    expires_at timestamptz NOT NULL,
    last_used_at timestamptz,
    rotated_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS oauth_refresh_lookup_idx
    ON oauth_refresh_tokens(token_hash)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS oauth_refresh_family_idx
    ON oauth_refresh_tokens(family_id);

CREATE TABLE IF NOT EXISTS oauth_access_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash text NOT NULL UNIQUE,
    token_prefix text NOT NULL,
    client_id text NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_id uuid REFERENCES oauth_refresh_tokens(id) ON DELETE SET NULL,
    scopes text[] NOT NULL,
    resource text NOT NULL,
    expires_at timestamptz NOT NULL,
    last_used_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS oauth_access_lookup_idx
    ON oauth_access_tokens(token_hash)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS oauth_access_client_idx
    ON oauth_access_tokens(client_id, expires_at DESC);

CREATE INDEX IF NOT EXISTS oauth_access_user_idx
    ON oauth_access_tokens(user_id, expires_at DESC);


-- v2.3 Disaster Recovery

-- Engram v2.3 - Disaster Recovery evidence and restore testing

CREATE TABLE IF NOT EXISTS dr_backup_artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_type text NOT NULL
        CHECK (artifact_type IN ('postgres','objects')),
    file_name text NOT NULL,
    file_path text NOT NULL,
    size_bytes bigint NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    sha256 text,
    encrypted boolean NOT NULL DEFAULT true,
    integrity_status text NOT NULL DEFAULT 'unknown'
        CHECK (integrity_status IN ('unknown','verified','failed')),
    integrity_error text,
    artifact_created_at timestamptz,
    retention_until timestamptz,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_checked_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(artifact_type, file_name)
);

CREATE INDEX IF NOT EXISTS dr_backup_artifacts_recent_idx
    ON dr_backup_artifacts(artifact_type, artifact_created_at DESC);

CREATE TABLE IF NOT EXISTS dr_restore_tests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','processing','passed','warning','failed')),
    requested_by text NOT NULL DEFAULT 'system',
    postgres_artifact_id uuid REFERENCES dr_backup_artifacts(id) ON DELETE SET NULL,
    object_artifact_id uuid REFERENCES dr_backup_artifacts(id) ON DELETE SET NULL,
    postgres_restore_ok boolean,
    object_extract_ok boolean,
    vector_extension_ok boolean,
    memory_count bigint,
    document_count bigint,
    object_file_count bigint,
    missing_object_refs bigint,
    database_size_bytes bigint,
    duration_seconds integer,
    error_message text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS dr_restore_tests_recent_idx
    ON dr_restore_tests(created_at DESC);

CREATE TABLE IF NOT EXISTS dr_replication_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','processing','passed','warning','failed','disabled')),
    requested_by text NOT NULL DEFAULT 'system',
    target text,
    postgres_file_name text,
    object_file_name text,
    postgres_present_remote boolean,
    object_present_remote boolean,
    files_copied integer NOT NULL DEFAULT 0,
    bytes_copied bigint NOT NULL DEFAULT 0,
    duration_seconds integer,
    error_message text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS dr_replication_runs_recent_idx
    ON dr_replication_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS dr_status (
    key text PRIMARY KEY,
    status text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    checked_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dr_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    action text NOT NULL
        CHECK (action IN ('scan','restore_test','replicate')),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','processing','completed','failed')),
    requested_by text NOT NULL,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS dr_requests_queue_idx
    ON dr_requests(status, created_at)
    WHERE status='queued';
