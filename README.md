# MemoryBank

> Self-hosted personal memory, source-ingestion and AI context platform.

MemoryBank gives you one controlled source of truth for personal knowledge. Humans use the web dashboard, software uses the REST API, and AI clients can use the same governed data through MCP.

**Current release:** `v2.1.0`  
**Recommended deployment:** Linux + Docker Compose + host-managed Cloudflare Tunnel

## Highlights

- PostgreSQL + pgvector memory store
- Hybrid semantic + full-text retrieval
- Local Ollama embeddings and local Qwen extraction
- Secure browser sessions and scoped API keys
- REST API + MCP
- Versioned memories and soft-delete approval workflow
- Bulk files, folders and safe ZIP ingestion
- PDF, DOCX, TXT, Markdown, CSV, JSON, YAML and log extraction
- ChatGPT export importer
- Unified candidate Memory Inbox
- Duplicate, related, update and conflict classification
- Entity graph
- Temporal / superseding memories
- Dynamic memory scoring
- Event timeline
- Memory health checks
- GitHub App continuous connector
- Browser page / selection / link / note capture
- Scheduled ingestion mesh with source provenance
- MinIO source-document storage
- Redis/RQ background workers
- Caddy local gateway
- Encrypted PostgreSQL and MinIO backup jobs
- No direct public database, Redis, Ollama or MinIO ports

## Architecture

```text
                         INTERNET
                            |
                    Cloudflare HTTPS/WAF
                            |
                 host cloudflared service
                            |
                    127.0.0.1:8080
                            |
                      Caddy Gateway
                       /         \
                      /           \
               Next.js Web     FastAPI
                                  |
              +-------------------+-------------------+
              |          |             |              |
          PostgreSQL    Redis         Ollama          MinIO
          + pgvector     RQ       embeddings/Qwen   documents
```

`backend` is an internal Docker network. Ollama also joins a dedicated `egress`
network so models can be pulled without exposing Ollama publicly.

## Quick start

```bash
git clone <YOUR_REPOSITORY_URL>
cd memorybank

cp .env.example .env
nano .env
```

Generate independent secrets:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
```

Use those values for PostgreSQL, Redis, MinIO and backup encryption. Keep matching
credentials consistent inside `DATABASE_URL`, `REDIS_URL` and MinIO settings.

Start the stack:

```bash
docker compose up -d --build
```

Pull local models:

```bash
docker compose exec ollama ollama pull all-minilm
docker compose exec ollama ollama pull qwen3:4b
```

Create an administrator:

```bash
docker compose exec -it api python scripts/create_admin.py
```

Health check:

```bash
curl http://127.0.0.1:8080/health
```

## Cloudflare Tunnel

MemoryBank intentionally does **not** include a `cloudflared` container.

Run your existing host-level `cloudflared` service and configure a published
hostname to:

```text
http://127.0.0.1:8080
```

That keeps the tunnel lifecycle separate from the application stack and avoids
putting the tunnel token in this repository.

## Upgrading an existing deployment

Database migrations live in `db/migrations/`.

Example:

```bash
sudo docker compose exec -T db sh -lc \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/migrations/004_knowledge_core.sql
```

See [`docs/UPGRADING.md`](docs/UPGRADING.md) before applying migrations.

## Repository layout

```text
backend/              FastAPI, MCP, workers and knowledge logic
web/                  Next.js dashboard
db/                   bootstrap schema and migrations
gateway/              Caddy configuration
ops/                  encrypted backup containers
docs/                 architecture, deployment and operations docs
.github/               CI, Dependabot and contribution templates
docker-compose.yml    production stack
.env.example          safe configuration template
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Upgrading](docs/UPGRADING.md)
- [Backup and restore](docs/BACKUP-RESTORE.md)
- [Operations](docs/OPERATIONS.md)
- [Roadmap](docs/ROADMAP.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Security

This application can contain extremely sensitive personal information.

Never commit:

- `.env`
- API keys
- Cloudflare tunnel tokens
- database dumps
- MinIO backups
- ChatGPT exports
- uploaded documents
- production logs containing credentials

See [SECURITY.md](SECURITY.md).

## License

This repository is currently **source-visible but not open source**. See [LICENSE](LICENSE).


## v2.1 Ingestion Mesh

See [GitHub Connector](docs/GITHUB-CONNECTOR.md) and [Browser Capture](docs/BROWSER-CAPTURE.md).
