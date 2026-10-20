-- Saved reflection snapshots. Originals remain untouched; regeneration is explicit.
CREATE TABLE IF NOT EXISTS project_briefs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL DEFAULT engram_current_project() REFERENCES projects(id),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
    snapshot jsonb NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS project_briefs_project_idx ON project_briefs(project_id,created_at DESC);
ALTER TABLE project_briefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_briefs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_access ON project_briefs;
CREATE POLICY project_access ON project_briefs
    USING (project_id=engram_current_project()) WITH CHECK (project_id=engram_current_project());
GRANT SELECT,INSERT,DELETE ON project_briefs TO engram_runtime;
