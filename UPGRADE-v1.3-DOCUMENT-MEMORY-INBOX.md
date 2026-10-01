# Engram v1.3 — Document Memory Inbox

This adds memory extraction for every document already uploaded to Engram.

## Install on Blackwall

Copy the patch ZIP to `/home/jayden/`, then:

```bash
cd /opt/memorybank

sudo unzip -o \
  /home/jayden/memorybank-v1.3-document-memory-inbox-patch.zip \
  -d /opt/memorybank
```

Then:

```bash
cd /opt/memorybank/memorybank
```

Apply the migration:

```bash
sudo docker compose exec -T db sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/migrations/003_document_memory_inbox.sql
```

Rebuild:

```bash
sudo docker compose build --no-cache api worker web
sudo docker compose up -d --force-recreate api worker web gateway
```

Verify:

```bash
sudo docker compose exec api python -c \
'from app.main import app; print([r.path for r in app.routes if "imports/documents" in getattr(r, "path", "")])'
```

Open:

```text
https://YOUR-MEMORY-DOMAIN/imports/documents
```

Then click **Analyse all existing**.

It reuses your existing local `qwen3:4b` model from the ChatGPT importer.
