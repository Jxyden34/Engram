ALTER TABLE projects ADD COLUMN IF NOT EXISTS retention_days integer
    CHECK (retention_days BETWEEN 30 AND 36500);
