CREATE TABLE IF NOT EXISTS instance_setup(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),chat_model text,completed_at timestamptz);
INSERT INTO instance_setup(singleton) VALUES(true) ON CONFLICT DO NOTHING;
GRANT SELECT,UPDATE ON instance_setup TO engram_runtime;
