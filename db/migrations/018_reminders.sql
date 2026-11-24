CREATE TABLE IF NOT EXISTS memory_reminders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL DEFAULT engram_current_project() REFERENCES projects(id),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    note text NOT NULL DEFAULT '',due_at timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done','dismissed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(user_id,memory_id,due_at)
);
CREATE INDEX IF NOT EXISTS reminder_due ON memory_reminders(project_id,user_id,due_at) WHERE status='pending';
ALTER TABLE memory_reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_reminders FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_access ON memory_reminders;
CREATE POLICY project_access ON memory_reminders USING(project_id=engram_current_project()) WITH CHECK(project_id=engram_current_project());
GRANT SELECT,INSERT,UPDATE,DELETE ON memory_reminders TO engram_runtime;
