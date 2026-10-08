-- Opt-in, project-scoped memory-agent scans and their execution history.
CREATE TABLE IF NOT EXISTS agent_scan_schedules (
    project_id uuid PRIMARY KEY REFERENCES projects(id),
    enabled boolean NOT NULL DEFAULT false,
    interval_hours integer NOT NULL DEFAULT 24 CHECK (interval_hours BETWEEN 24 AND 720),
    next_scan_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_scan_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL DEFAULT engram_current_project() REFERENCES projects(id),
    trigger_type text NOT NULL CHECK (trigger_type IN ('manual', 'scheduled')),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    result jsonb,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS agent_scan_runs_project_idx
    ON agent_scan_runs(project_id, created_at DESC);

ALTER TABLE agent_scan_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_scan_schedules FORCE ROW LEVEL SECURITY;
CREATE POLICY project_access ON agent_scan_schedules
    USING (project_id = engram_current_project())
    WITH CHECK (project_id = engram_current_project());
ALTER TABLE agent_scan_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_scan_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY project_access ON agent_scan_runs
    USING (project_id = engram_current_project())
    WITH CHECK (project_id = engram_current_project());

GRANT SELECT, INSERT, UPDATE, DELETE ON agent_scan_schedules, agent_scan_runs TO engram_runtime;
