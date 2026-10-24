-- Append retained action records; undo records a reversal instead of deleting history.
CREATE TABLE IF NOT EXISTS memory_lifecycle_actions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL DEFAULT engram_current_project() REFERENCES projects(id),
    memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK(kind IN ('archive','restore','consolidation')),
    previous_archived_at timestamptz,
    expected_updated_at timestamptz NOT NULL,
    actor text NOT NULL,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    undone_at timestamptz,
    undone_by text,
    undo_reason text
);
CREATE INDEX IF NOT EXISTS lifecycle_recent_idx ON memory_lifecycle_actions(project_id,created_at DESC);
ALTER TABLE memory_lifecycle_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_lifecycle_actions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_access ON memory_lifecycle_actions;
CREATE POLICY project_access ON memory_lifecycle_actions
    USING(project_id=engram_current_project()) WITH CHECK(project_id=engram_current_project());
GRANT SELECT,INSERT,DELETE ON memory_lifecycle_actions TO engram_runtime;
GRANT UPDATE(undone_at,undone_by,undo_reason) ON memory_lifecycle_actions TO engram_runtime;
