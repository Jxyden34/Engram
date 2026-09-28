# Engram v1.2 — ChatGPT Importer + Candidate Memory Inbox

This upgrade adds a dedicated ChatGPT-export distillation workflow.

## 1. Apply the patch

Copy the patch ZIP to Blackwall and extract it from `/opt/memorybank` so that the top-level
`memorybank/` directory overlays the existing project.

Keep your existing `.env`.

## 2. Add settings

Add to `.env`:

```dotenv
CHAT_MODEL=qwen3:4b
CHAT_IMPORT_CHUNK_CHARS=14000
CHAT_IMPORT_MAX_CANDIDATES_PER_CHUNK=12
```

## 3. Apply the database migration

From the project directory:

```bash
sudo docker compose exec -T db \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  < db/migrations/002_chatgpt_importer.sql
```

If your shell does not export the values from `.env`, use:

```bash
set -a
. ./.env
set +a

sudo docker compose exec -T db \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  < db/migrations/002_chatgpt_importer.sql
```

The SQL uses `IF NOT EXISTS`, so re-running it is safe.

## 4. Rebuild the application

```bash
sudo docker compose build --no-cache api worker web
sudo docker compose up -d --force-recreate api worker web gateway
```

## 5. Pull the local extraction model

Ollama needs outbound access as configured in the previous deployment step.

```bash
sudo docker compose exec ollama ollama pull qwen3:4b
sudo docker compose exec ollama ollama list
```

## 6. Verify

```bash
sudo docker compose exec api python -c \
'from app.main import app; print([r.path for r in app.routes if "imports/chatgpt" in getattr(r, "path", "")])'
```

You should see the ChatGPT import routes.

Open:

```text
https://YOUR-HOST/imports/chatgpt
```

## 7. Use it

1. Download your ChatGPT data export.
2. Upload the entire ZIP under **Documents → Bulk ingest**.
3. Wait for `conversations.json` (or `conversations*.json`) to appear in the document library.
4. Open **Memory Inbox**.
5. Click **Analyse** next to the conversation export.
6. Watch conversation progress.
7. Review candidates.
8. Accept, edit, or reject them.
9. Use **Accept all safe** only when you are comfortable with the conservative automatic filter.

## Notes

A large ChatGPT history can take significant time and CPU because every conversation is processed
locally. The RQ worker performs the work outside the web request, so closing the browser does not stop
an import already queued on the server.

The importer reads the active conversation branch when the export includes `current_node`; otherwise
it falls back to chronological messages.

Accepted memories retain source provenance in the `metadata` JSON.
