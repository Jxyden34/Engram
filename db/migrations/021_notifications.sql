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

CREATE TABLE IF NOT EXISTS notification_telegram (
    project_id uuid PRIMARY KEY DEFAULT engram_current_project() REFERENCES projects(id),
    enabled boolean NOT NULL DEFAULT false,
    chat_id text NOT NULL CHECK (chat_id ~ '^-?[0-9]{1,20}$'),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS notification_deliveries (
    project_id uuid NOT NULL DEFAULT engram_current_project(),
    notification_id uuid NOT NULL,
    generation integer NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    delivered_at timestamptz,
    last_error text,
    PRIMARY KEY(project_id,notification_id,generation),
    FOREIGN KEY(project_id,notification_id) REFERENCES notifications(project_id,id) ON DELETE CASCADE
);
ALTER TABLE notification_telegram ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_telegram FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_access ON notification_telegram;
CREATE POLICY project_access ON notification_telegram USING (project_id=engram_current_project()) WITH CHECK (project_id=engram_current_project());
ALTER TABLE notification_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_deliveries FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_access ON notification_deliveries;
CREATE POLICY project_access ON notification_deliveries USING (project_id=engram_current_project()) WITH CHECK (project_id=engram_current_project());
GRANT SELECT,INSERT,UPDATE,DELETE ON notification_telegram,notification_deliveries TO engram_runtime;
