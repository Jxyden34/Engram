CREATE TABLE IF NOT EXISTS notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL DEFAULT engram_current_project() REFERENCES projects(id),
    kind text NOT NULL CHECK (kind IN ('connector_failure','important_conflict','backup_failure','important_update','stale_credentials','unresolved_candidates')),
    source_key text NOT NULL,
    title text NOT NULL,
    detail text NOT NULL,
    href text NOT NULL CHECK (href LIKE '/%' AND href NOT LIKE '//%'),
    severity text NOT NULL CHECK (severity IN ('info','warning','critical')),
    generation integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    UNIQUE(project_id, kind, source_key),
    UNIQUE(project_id, id)
);
CREATE INDEX IF NOT EXISTS notifications_active_idx ON notifications(project_id, created_at DESC) WHERE resolved_at IS NULL;
CREATE TABLE IF NOT EXISTS notification_receipts (
    project_id uuid NOT NULL DEFAULT engram_current_project() REFERENCES projects(id),
    notification_id uuid NOT NULL,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    generation integer NOT NULL,
    read_at timestamptz,
    dismissed_at timestamptz,
    PRIMARY KEY(project_id, notification_id, user_id),
    FOREIGN KEY(project_id, notification_id) REFERENCES notifications(project_id, id) ON DELETE CASCADE
);
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_access ON notifications;
CREATE POLICY project_access ON notifications USING (project_id=engram_current_project()) WITH CHECK (project_id=engram_current_project());
ALTER TABLE notification_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_access ON notification_receipts;
CREATE POLICY project_access ON notification_receipts USING (project_id=engram_current_project()) WITH CHECK (project_id=engram_current_project());
GRANT SELECT, INSERT, UPDATE, DELETE ON notifications, notification_receipts TO engram_runtime;
