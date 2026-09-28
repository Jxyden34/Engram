# Engram v1.4 — Unified Memory Inbox

This patch replaces the separate ChatGPT Inbox and Document Inbox with one streamlined **Memory Inbox**.

It includes the generic document-memory analyser from v1.3, so if you have not installed v1.3 yet, do not install it separately.

## What changes

- one sidebar entry: **Memory Inbox**
- one route: `/imports`
- one **Analyse everything** button
- one combined candidate queue
- filters for **All sources / ChatGPT / Documents**
- one **Accept all safe** action
- ChatGPT `conversations*.json` goes only through the ChatGPT-aware importer
- normal documents go only through the generic document analyser
- old `/imports/chatgpt` and `/imports/documents` links redirect to `/imports`

## Install on Blackwall

Copy:

```text
memorybank-v1.4-unified-memory-inbox-patch.zip
```

to:

```text
/home/jayden/
```

Then:

```bash
cd /opt/memorybank

sudo unzip -o \
  /home/jayden/memorybank-v1.4-unified-memory-inbox-patch.zip \
  -d /opt/memorybank
```

Move into the project:

```bash
cd /opt/memorybank/memorybank
```

## Apply the document-memory migration

This is safe to run even if you already installed v1.3 because the SQL uses `IF NOT EXISTS`.

```bash
sudo docker compose exec -T db sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/migrations/003_document_memory_inbox.sql
```

## Rebuild

```bash
sudo docker compose build --no-cache api worker web

sudo docker compose up -d \
  --force-recreate \
  api worker web gateway
```

## Verify

API:

```bash
sudo docker compose exec api python -c \
'from app.main import app; print([r.path for r in app.routes if "imports/" in getattr(r, "path", "")])'
```

Web files:

```bash
grep -n "Memory Inbox" web/components/Shell.tsx
grep -n "Analyse everything" web/app/imports/page.tsx
```

Then hard-refresh the browser:

```text
Ctrl + F5
```

Open:

```text
https://YOUR-MEMORY-DOMAIN/imports
```

## How it behaves

`Analyse everything`:

1. queues all ready normal documents that do not already have pending candidates
2. queues ChatGPT conversation exports that have not already completed an import
3. does not send `conversations*.json` through the generic document analyser
4. leaves existing completed ChatGPT imports alone unless you explicitly click **Re-analyse**

The same local `qwen3:4b` model is reused. No new Ollama model is required.
