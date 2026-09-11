# MemoryBank

A self-hosted personal memory and AI context platform.

MemoryBank is designed around one rule: **you own the source of truth**. Humans use the dashboard, software uses the REST API, and AI clients use the same controlled data layer through MCP.

## What ships in this repository

- Public web dashboard with secure login
- PostgreSQL + pgvector memory store
- Hybrid semantic + PostgreSQL full-text search
- Ollama local embeddings
- Memory types, tags, confidence and importance
- Full memory version history
- Relationships between memories
- AI deletion request / human approval workflow
- Audit log
- Scoped bearer API keys
- Remote MCP server for AI clients
- Document upload, extraction, chunking and semantic search
- Bulk folder ingestion and safe ZIP archive expansion
- ChatGPT export importer with local AI memory distillation
- Candidate Memory Inbox with duplicate/update/conflict hints
- MinIO source-document storage with object versioning
- Redis + RQ document ingestion worker
- Caddy application gateway
- Cloudflare Tunnel public ingress
- Encrypted PostgreSQL and object-store backups
- No public database, Redis, Ollama, or MinIO ports

## Architecture

```text
                           INTERNET
                               |
                      Cloudflare HTTPS/WAF
                               |
                    outbound Cloudflare Tunnel
                               |
                               v
                       +---------------+
                       | Caddy Gateway |
                       |    :8080      |
                       +-------+-------+
                               |
                 +-------------+-------------+
                 |                           |
                 v                           v
          +-------------+             +-------------+
          | Next.js Web |             | FastAPI API |
          | dashboard   |             | REST + MCP  |
          +-------------+             +------+------+
                                             |
             +-------------------------------+--------------------+
             |                |                 |                 |
             v                v                 v                 v
       PostgreSQL 18       Redis 8           Ollama             MinIO
       + pgvector          RQ queue         embeddings        documents
             |                                  |
             +--------- semantic search --------+
```

Only `gateway` and `cloudflared` are on the edge network. PostgreSQL, Redis, Ollama and MinIO live on Docker's internal backend network.

## Important security model

### Browser

The dashboard uses an opaque random server-side session. The browser receives:

- `memory_session`: HttpOnly cookie
- `memory_csrf`: CSRF cookie that the frontend echoes in `X-CSRF-Token`

Passwords are hashed with Argon2.

### AI/API clients

API keys are opaque random credentials. Only a SHA-256 digest is stored in PostgreSQL.

Recommended AI scopes:

```text
memory:read
memory:write
memory:delete_request
document:read
mcp:use
```

Do **not** grant an AI:

```text
memory:delete_approve
keys:admin
audit:read
```

The MCP interface deliberately has no tool for approving deletion.

### Destructive actions

Memory deletion is a soft delete. An AI can request it, but an administrator must approve it in the dashboard.

Previous states are stored in `memory_versions`.

## Prerequisites

Recommended host:

- Ubuntu Server 24.04 LTS or newer
- Docker Engine + Docker Compose plugin
- 4 CPU cores minimum
- 8 GB RAM minimum, 16 GB comfortable
- 30 GB+ free storage
- A Cloudflare-managed domain
- Outbound internet access

No inbound router port-forward is required.

## Deploy

### 1. Extract and configure

```bash
cd memorybank
cp .env.example .env
```

Generate four different secrets:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
```

Use them for:

```dotenv
POSTGRES_PASSWORD=
REDIS_PASSWORD=
MINIO_ROOT_PASSWORD=
BACKUP_ENCRYPTION_PASSWORD=
```

Make sure `DATABASE_URL`, `REDIS_URL` and `MINIO_SECRET_KEY` contain the same matching passwords.

Set your real hostname:

```dotenv
PUBLIC_HOST=memory.example.com
PUBLIC_ORIGIN=https://memory.example.com
COOKIE_SECURE=true
```

### 2. Create a Cloudflare Tunnel

In Cloudflare, create a remotely managed Tunnel.

Create a public hostname / published application:

```text
Hostname: memory.example.com
Service:  http://gateway:8080
```

Copy the tunnel token into:

```dotenv
CLOUDFLARE_TUNNEL_TOKEN=eyJ...
```

`cloudflared` creates an outbound-only connection. You do not expose a home IP or open an inbound firewall port.

### 3. Start the platform

```bash
docker compose up -d --build
```

Check it:

```bash
docker compose ps
curl http://127.0.0.1:8080/health
```

### 4. Pull the embedding model

```bash
docker compose exec ollama ollama pull all-minilm
```

The current `all-minilm` Ollama model emits 384-dimensional embeddings, matching `vector(384)` in the schema.

### 5. Create your administrator

```bash
docker compose exec -it api python scripts/create_admin.py
```

Enter your username and password interactively. No administrator password needs to live in `.env`.

Then visit:

```text
https://memory.example.com
```

## First useful memory

Use **New memory** in the dashboard, or:

```bash
curl -X POST https://memory.example.com/api/v1/memories \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Primary home server",
    "content": "Venus is my primary Ubuntu server.",
    "memory_type": "infrastructure",
    "importance": 8,
    "confidence": 1,
    "tags": ["linux", "server"],
    "source_type": "manual"
  }'
```

## Give an AI access

Sign in to the dashboard and open **AI & API**.

Create an AI key. It is displayed once.

MCP endpoint:

```text
https://memory.example.com/mcp
```

Header:

```text
Authorization: Bearer mem_live_xxxxxxxxx
```

Available MCP tools:

```text
memory_search
document_search
memory_get
memory_add
memory_update
memory_request_delete
memory_relations
```

The server uses the current MCP Python SDK v2 Streamable HTTP transport.

## REST surface

Useful endpoints:

```text
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
GET    /api/v1/auth/me

GET    /api/v1/stats

GET    /api/v1/memories
POST   /api/v1/memories
GET    /api/v1/memories/{id}
PATCH  /api/v1/memories/{id}
GET    /api/v1/memories/{id}/versions
GET    /api/v1/memories/{id}/relations
POST   /api/v1/memories/{id}/relations
POST   /api/v1/memories/{id}/request-delete
POST   /api/v1/memories/{id}/restore

POST   /api/v1/search

GET    /api/v1/deletion-requests
POST   /api/v1/deletion-requests/{id}/approve
POST   /api/v1/deletion-requests/{id}/reject

GET    /api/v1/documents
POST   /api/v1/documents
POST   /api/v1/documents/bulk

GET    /api/v1/imports/chatgpt/documents
GET    /api/v1/imports/chatgpt/jobs
POST   /api/v1/imports/chatgpt/jobs
GET    /api/v1/imports/chatgpt/candidates
PATCH  /api/v1/imports/chatgpt/candidates/{id}
POST   /api/v1/imports/chatgpt/candidates/{id}/accept
POST   /api/v1/imports/chatgpt/candidates/{id}/reject
POST   /api/v1/imports/chatgpt/candidates/accept-safe
GET    /api/v1/documents/{id}/download

GET    /api/v1/audit

GET    /api/v1/keys
POST   /api/v1/keys
DELETE /api/v1/keys/{id}

POST   /mcp
```

Interactive OpenAPI docs are at:

```text
https://memory.example.com/api/docs
```

## Document ingestion

Supported extraction in this build:

- PDF
- DOCX
- TXT
- Markdown
- CSV
- JSON
- YAML
- logs

Flow:

```text
upload
  -> MinIO original file
  -> Redis/RQ ingestion job
  -> text extraction
  -> overlapping chunks
  -> local Ollama embeddings
  -> pgvector
  -> searchable from dashboard + MCP
```

The source file remains intact in MinIO.



## Bulk folders and ZIP archives

The **Documents** page includes a bulk-ingest drop zone.

You can:

- select many files at once
- select an entire folder recursively
- drag folders into the page in browsers that expose directory entries
- upload ZIP archives containing supported documents
- mix ZIPs, folders and loose files in the same batch

The browser preserves folder-relative names where possible, so a source like:

```text
ChatGPT Export/
  conversations/
    kubernetes.md
  account/
    profile.json
```

appears in the document library with its relative path intact.

ZIP archives are treated as transport containers. Supported files inside them are extracted and stored individually in MinIO, then queued for normal document processing.

Protections include:

- no absolute archive paths
- no `..` traversal
- no ZIP symlinks
- no encrypted ZIP entries
- expanded-size limit
- entry-count limit
- suspicious compression-ratio rejection
- hidden operating-system junk skipped
- SHA-256 duplicate detection

Defaults are controlled in `.env`:

```dotenv
MAX_UPLOAD_MB=50
BULK_MAX_FILES=1000
BULK_MAX_TOTAL_MB=500
ZIP_MAX_EXPANDED_MB=500
```

These are server-side safety limits, not just browser hints.



## ChatGPT export → Candidate Memory Inbox

MemoryBank can turn a ChatGPT `conversations.json` export into reviewable durable memories.

The flow is:

```text
ChatGPT export ZIP
  -> Documents / Bulk ingest
  -> conversations*.json discovered
  -> local Qwen model reads conversations
  -> candidate memories extracted
  -> pgvector finds nearest existing memory
  -> local comparison classifies:
       new / duplicate / related / updates / conflicts
  -> Memory Inbox
  -> human accept / edit / reject
  -> permanent memory with provenance
```

The extraction model is local through Ollama:

```dotenv
CHAT_MODEL=qwen3:4b
CHAT_IMPORT_CHUNK_CHARS=14000
CHAT_IMPORT_MAX_CANDIDATES_PER_CHUNK=12
```

Install it before starting an import:

```bash
docker compose exec ollama ollama pull qwen3:4b
```

The importer does not send conversation content to a third-party LLM.

### Candidate safety

`Accept all safe` only accepts candidates that:

- have confidence >= 0.85
- are classified as `new`
- have no existing memory >= 0.78 semantic similarity

Candidates classified as `duplicate`, `updates`, `conflicts` or `related` remain for manual review.

Accepted memories preserve:

- ChatGPT conversation title
- external conversation ID when available
- source export document
- first/last message timestamps
- a source excerpt
- originating candidate ID

## Backups

Two backup services start immediately and then run every 24 hours:

- `db-backup`
- `object-backup`

Both encrypt output using AES-256-CBC with PBKDF2 and place files under:

```text
./backups/postgres/
./backups/objects/
```

Default retention is 14 days.

These local backup directories should themselves be copied off-host. For example, use an encrypted restic repository on another server or object store.

### Restore PostgreSQL

Decrypt:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in backups/postgres/memorybank-YYYYMMDDTHHMMSSZ.dump.enc \
  -out /tmp/memorybank.dump \
  -pass env:BACKUP_ENCRYPTION_PASSWORD
```

Restore into an empty database using `pg_restore`.

## Local-only test mode

For testing without Cloudflare:

```dotenv
PUBLIC_HOST=localhost
PUBLIC_ORIGIN=http://localhost:8080
COOKIE_SECURE=false
```

Then use:

```text
http://127.0.0.1:8080
```

Switch `COOKIE_SECURE=true` before public deployment.

## Operations

```bash
docker compose ps
docker compose logs -f --tail=150
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f cloudflared
```

Database shell:

```bash
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Re-pull the embedding model:

```bash
docker compose exec ollama ollama pull all-minilm
```

## Sensible next milestones

The platform is intentionally designed so these can slot in without rewriting the core:

- OAuth 2.1 / OIDC with Authentik or Keycloak
- Passkeys / WebAuthn
- Multiple users and isolated namespaces
- Entity extraction and automatic knowledge graph construction
- Contradiction detection and memory supersession
- Candidate-memory approval mode for untrusted AI clients
- Email, calendar, GitHub and chat importers
- Photo metadata and image embeddings
- Temporal queries, e.g. "what did I believe in March?"
- Automatic data-retention policies
- Encrypted off-site restic backups
- Prometheus/Grafana metrics
- High availability for API and PostgreSQL
- Mobile PWA / push approval notifications

## Design note

The database is the source of truth. The vector embedding is merely an index. If embeddings are ever changed, every vector can be rebuilt from the stored text.

That prevents the classic RAG trap where the "memory" becomes a mysterious pile of vectors with no clean human-readable canonical data.
