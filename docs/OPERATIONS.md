# MemoryBank Operations

This document covers common operational checks for MemoryBank v2.1.

---

# Service status

```bash
cd /opt/memorybank/memorybank
sudo docker compose ps
```

Expected major services include:

```text
db
redis
ollama
minio
api
worker
web
gateway
connector-scheduler
```

---

# Health check

```bash
curl http://127.0.0.1:8080/health
```

For the public hostname:

```bash
curl https://YOUR-MEMORYBANK-DOMAIN/health
```

---

# Logs

API:

```bash
sudo docker compose logs -f api
```

Worker:

```bash
sudo docker compose logs -f worker
```

Web:

```bash
sudo docker compose logs -f web
```

Connector scheduler:

```bash
sudo docker compose logs -f connector-scheduler
```

Gateway:

```bash
sudo docker compose logs -f gateway
```

---

# Queue status

Check RQ:

```bash
sudo docker compose exec worker sh -lc   'rq info --url "$REDIS_URL"'
```

This is useful when document ingestion or connector work appears stuck.

---

# PostgreSQL

Check database size:

```bash
sudo docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT current_database(),
       pg_size_pretty(pg_database_size(current_database()));
"'
```

Check active sessions:

```bash
sudo docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS running_for,
    left(query, 160) AS query
FROM pg_stat_activity
WHERE datname=current_database()
  AND pid <> pg_backend_pid()
ORDER BY query_start;
"'
```

---

# Documents

Recent documents:

```bash
sudo docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT
    filename,
    source_type,
    status,
    created_at,
    processed_at
FROM documents
ORDER BY created_at DESC
LIMIT 20;
"'
```

---

# GitHub connector

Recent sync runs:

```bash
sudo docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT
    c.name,
    r.status,
    r.items_seen,
    r.items_changed,
    r.items_skipped,
    r.error_count,
    r.error_message,
    r.started_at,
    r.completed_at
FROM connector_sync_runs r
JOIN connectors c ON c.id=r.connector_id
ORDER BY r.created_at DESC
LIMIT 10;
"'
```

Recent GitHub items:

```bash
sudo docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT
    item_type,
    title,
    external_url,
    last_seen_at
FROM connector_items
ORDER BY last_seen_at DESC
LIMIT 20;
"'
```

Recent GitHub documents:

```bash
sudo docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT
    filename,
    source_type,
    source_ref,
    status,
    created_at
FROM documents
WHERE source_type='\''github'\''
ORDER BY created_at DESC
LIMIT 20;
"'
```

---

# GitHub credentials

Check App ID:

```bash
sudo docker compose exec api sh -lc   'echo "$GITHUB_APP_ID"'
```

Check private key mount:

```bash
sudo docker compose exec api   ls -l /run/secrets/github-app.pem
```

---

# Ollama

List models:

```bash
sudo docker compose exec ollama ollama list
```

Expected models:

```text
all-minilm
qwen3:4b
```

---

# MinIO

Check container status:

```bash
sudo docker compose ps minio
```

Review logs:

```bash
sudo docker compose logs minio --tail=100
```

---

# Cloudflare Tunnel

Cloudflare Tunnel runs on the host.

Status:

```bash
sudo systemctl status cloudflared
```

Restart:

```bash
sudo systemctl restart cloudflared
```

Logs:

```bash
sudo journalctl -u cloudflared -n 100 --no-pager
```

---

# Web application rebuild

If the web UI needs rebuilding:

```bash
sudo docker compose build --no-cache --progress=plain web
```

Then:

```bash
sudo docker compose up -d --force-recreate web gateway
```

If the build fails, inspect the TypeScript or Next.js error above the final Dockerfile failure line.

---

# Backend rebuild

```bash
sudo docker compose build --no-cache api worker connector-scheduler
```

Then:

```bash
sudo docker compose up -d   --force-recreate   api worker connector-scheduler
```

---

# Memory Inbox

Candidate memories may arrive from:

```text
documents
ChatGPT imports
GitHub
browser capture
```

They should remain candidates until reviewed.

Use the unified Memory Inbox to:

- accept
- edit
- reject
- bulk accept safe candidates

---

# Knowledge enrichment

Knowledge enrichment derives:

- entities
- relationships
- events
- temporal context

Run enrichment from the Knowledge Graph interface when new permanent memories have been added.

---

# Browser Capture

Browser Capture uses a dedicated API key with:

```text
capture:write
```

If the browser device is lost:

1. open AI & API
2. revoke the capture key
3. generate a new one
4. update the extension

---

# Backup check

Create and validate a database backup regularly:

```bash
sudo docker compose exec db sh -lc   'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/memorybank-check.dump'
```

Validate:

```bash
sudo docker compose exec db   pg_restore --list /tmp/memorybank-check.dump | head
```

---

# Disk usage

Host:

```bash
df -h
```

Docker:

```bash
sudo docker system df
```

Volumes:

```bash
sudo docker volume ls
```

Do not run destructive Docker cleanup commands blindly on a production MemoryBank host.

---

# Routine maintenance

Recommended weekly checks:

1. `docker compose ps`
2. `/health`
3. worker queue depth
4. failed connector syncs
5. PostgreSQL size
6. disk free space
7. recent backups
8. MinIO health
9. Ollama models
10. Cloudflare Tunnel status
11. unresolved Memory Inbox candidates
12. Memory Health dashboard

---

# Incident triage

If MemoryBank is unreachable:

```text
1. Check Caddy
2. Check API
3. Check web
4. Check Cloudflare Tunnel
5. Check PostgreSQL
6. Check Redis
```

If ingestion is stuck:

```text
1. Check worker
2. Check Redis
3. Check queue
4. Check document status
5. Check Ollama
```

If GitHub sync is stuck:

```text
1. Check connector-scheduler
2. Check worker
3. Check App ID
4. Check private key mount
5. Check installation ID
6. Check GitHub App repository permissions
7. Inspect connector_sync_runs
```


# OAuth / MCP identity

Protected resource metadata:

```bash
curl -s https://YOUR-HOST/.well-known/oauth-protected-resource/mcp
```

Authorization server metadata:

```bash
curl -s https://YOUR-HOST/.well-known/oauth-authorization-server
```

MCP without credentials should return `401` with a `WWW-Authenticate` discovery challenge:

```bash
curl -i https://YOUR-HOST/mcp
```

Review OAuth clients and grants from **AI, API & OAuth** in the web dashboard.


# Disaster Recovery

Monitor:

```bash
sudo docker compose logs -f dr-monitor
```

Dashboard:

```text
/disaster-recovery
```

Queue a restore test:

```bash
make dr-test
```

Queue off-site replication:

```bash
make dr-replicate
```

Recent evidence:

```bash
make dr-status
```
