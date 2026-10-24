-- Pins protect retrieval priority from age decay; they never override access or validity.
ALTER TABLE memories ADD COLUMN IF NOT EXISTS pinned boolean NOT NULL DEFAULT false;
