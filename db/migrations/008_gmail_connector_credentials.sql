-- Gmail refresh tokens are encrypted by the application before storage.
ALTER TABLE connectors
    ADD COLUMN IF NOT EXISTS credential_ciphertext text;
