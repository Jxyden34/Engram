-- Reversible archival, separate from soft deletion and historical validity.
ALTER TABLE memories ADD COLUMN IF NOT EXISTS archived_at timestamptz;
CREATE INDEX IF NOT EXISTS memories_archival_idx ON memories(project_id,archived_at);
