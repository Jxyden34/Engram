-- Bind OAuth grants and tokens to the project selected at consent time.
-- Existing grants remain in Personal.
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'oauth_consents', 'oauth_authorization_codes',
        'oauth_refresh_tokens', 'oauth_access_tokens'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id)', table_name);
        EXECUTE format('UPDATE %I SET project_id = %L WHERE project_id IS NULL',
                       table_name, '00000000-0000-0000-0000-000000000001');
        EXECUTE format('ALTER TABLE %I ALTER COLUMN project_id SET DEFAULT engram_current_project()', table_name);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN project_id SET NOT NULL', table_name);
    END LOOP;
END $$;

ALTER TABLE oauth_consents DROP CONSTRAINT IF EXISTS oauth_consents_client_id_user_id_resource_key;
CREATE UNIQUE INDEX IF NOT EXISTS oauth_consents_project_unique
    ON oauth_consents(client_id, user_id, resource, project_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO engram_runtime;

ALTER TABLE agent_proposals DROP CONSTRAINT IF EXISTS agent_proposals_proposal_type_check;
ALTER TABLE agent_proposals ADD CONSTRAINT agent_proposals_proposal_type_check
    CHECK (proposal_type IN ('duplicate', 'conflict', 'stale', 'missing_provenance', 'low_confidence'));
