-- Installation-wide entitlement, independent of project selection.
CREATE TABLE IF NOT EXISTS commercial_license (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    installation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    use_mode text NOT NULL DEFAULT 'personal' CHECK (use_mode IN ('personal', 'commercial')),
    license_key text,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO commercial_license(singleton) VALUES (true) ON CONFLICT DO NOTHING;
GRANT SELECT, UPDATE ON commercial_license TO engram_runtime;
