CREATE TABLE IF NOT EXISTS instance_branding (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    name text NOT NULL DEFAULT 'Engram',
    tagline text NOT NULL DEFAULT 'private cognition layer',
    accent text NOT NULL DEFAULT '#b6ff4a',
    logo text NOT NULL DEFAULT ''
);
INSERT INTO instance_branding(singleton) VALUES(true) ON CONFLICT DO NOTHING;
GRANT SELECT,UPDATE ON instance_branding TO engram_runtime;
