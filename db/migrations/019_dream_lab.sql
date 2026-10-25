-- Generated prototypes remain separate from source memories and live infrastructure.
CREATE TABLE IF NOT EXISTS dream_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL DEFAULT engram_current_project() REFERENCES projects(id),
    parent_id uuid REFERENCES dream_runs(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','ready','kept','failed')),
    direction text NOT NULL DEFAULT '',
    sources jsonb NOT NULL DEFAULT '[]',
    artifact jsonb,
    report jsonb NOT NULL DEFAULT '[]',
    error_message text,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS dream_runs_recent ON dream_runs(project_id,created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS dream_one_active ON dream_runs(project_id) WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS dream_schedules (
    project_id uuid PRIMARY KEY DEFAULT engram_current_project() REFERENCES projects(id),
    enabled boolean NOT NULL DEFAULT false,
    hour_utc integer NOT NULL DEFAULT 2 CHECK(hour_utc BETWEEN 0 AND 23),
    next_run_at timestamptz,
    created_by text NOT NULL
);
ALTER TABLE dream_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE dream_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE dream_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE dream_schedules FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_access ON dream_runs;
CREATE POLICY project_access ON dream_runs USING(project_id=engram_current_project()) WITH CHECK(project_id=engram_current_project());
DROP POLICY IF EXISTS project_access ON dream_schedules;
CREATE POLICY project_access ON dream_schedules USING(project_id=engram_current_project()) WITH CHECK(project_id=engram_current_project());
GRANT SELECT,INSERT,UPDATE,DELETE ON dream_runs,dream_schedules TO engram_runtime;
