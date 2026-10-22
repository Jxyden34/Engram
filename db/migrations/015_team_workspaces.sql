ALTER TABLE users ADD COLUMN IF NOT EXISTS team_only boolean NOT NULL DEFAULT false;
CREATE TABLE IF NOT EXISTS project_members (
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role text NOT NULL CHECK(role IN ('owner','editor','viewer')),
    PRIMARY KEY(project_id,user_id)
);
CREATE TABLE IF NOT EXISTS team_invitations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    username text NOT NULL,
    role text NOT NULL CHECK(role IN ('owner','editor','viewer')),
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL DEFAULT now()+interval '48 hours',
    accepted_at timestamptz,
    revoked_at timestamptz
);
GRANT SELECT,INSERT,UPDATE,DELETE ON project_members,team_invitations TO engram_runtime;
