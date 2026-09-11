# MemoryBank v2.1 — Ingestion Mesh + Browser Capture

v2.1 adds:

- connector framework and scheduler
- GitHub App continuous sync
- repository/readme/docs/issues/pull-request ingestion
- optional source-code ingestion
- source provenance on documents
- automatic candidate-memory analysis for connector sources
- Browser Capture REST endpoint
- Chrome/Edge Manifest V3 capture extension
- dedicated `capture:write` API scope
- Connectors dashboard

## 1. Back up PostgreSQL

```bash
cd /opt/memorybank/memorybank

sudo docker compose exec db sh -lc \
  'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/memorybank-pre-v2.1.dump'

sudo docker compose exec db \
  pg_restore --list /tmp/memorybank-pre-v2.1.dump | head -30
```

## 2. Stop the worker during migration

```bash
sudo docker compose stop worker connector-scheduler 2>/dev/null || true
```

## 3. Extract the patch

Copy the patch to `/home/jayden/`, then:

```bash
cd /opt/memorybank

sudo unzip -o \
  /home/jayden/memorybank-v2.1-ingestion-mesh-patch.zip \
  -d /opt/memorybank

cd /opt/memorybank/memorybank
```

## 4. Apply migration 005

```bash
sudo docker compose exec -T db sh -lc \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/migrations/005_ingestion_mesh.sql
```

## 5. Configure GitHub App credentials

Create the secrets directory if needed:

```bash
mkdir -p secrets
chmod 700 secrets
```

Put your GitHub App private key here:

```text
secrets/github-app.pem
```

Then:

```bash
chmod 600 secrets/github-app.pem
```

Add to `.env`:

```dotenv
GITHUB_APP_ID=YOUR_APP_ID
GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/github-app.pem
CONNECTOR_SCHEDULER_INTERVAL_SECONDS=60
GITHUB_MAX_ITEMS_PER_SYNC=300
GITHUB_MAX_FILE_KB=512
CAPTURE_MAX_CHARS=500000
```

You can leave `GITHUB_APP_ID` blank until you are ready to configure GitHub. Browser Capture works independently.

## 6. Rebuild

```bash
sudo docker compose build --no-cache api worker web connector-scheduler

sudo docker compose up -d \
  --force-recreate \
  api worker web gateway connector-scheduler
```

## 7. Verify

```bash
sudo docker compose ps
```

Check routes:

```bash
sudo docker compose exec api python -c \
'from app.main import app; print([r.path for r in app.routes if "connectors" in getattr(r,"path","") or "capture" in getattr(r,"path","")])'
```

Expected route families:

```text
/api/v1/connectors
/api/v1/connectors/capabilities
/api/v1/connectors/{connector_id}/sync
/api/v1/connectors/runs
/api/v1/capture
```

## 8. Open the dashboard

Hard refresh:

```text
Ctrl + F5
```

Open:

```text
/connectors
```

## 9. Browser extension

The extension is included under:

```text
extensions/memorybank-capture
```

Generate a capture key under **AI & API**.

Load the directory unpacked in Chrome/Edge developer mode and configure your MemoryBank public origin + capture key.
