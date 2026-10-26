# Engram

> Your knowledge. Your context. Your server.

Stop rebuilding context from scattered documents, saved pages and old conversations.
Engram brings them into a personal memory platform you host yourself, with local
Ollama processing, source-aware search and controlled access for your AI clients.

**[Explore Engram](https://jxyden34.github.io/Engram/)** ·
**[Set up your server](docs/DEPLOYMENT.md)** ·
**[Connect an MCP client](https://jxyden34.github.io/Engram/mcp.html)** ·
**[Report feedback](https://github.com/Jxyden34/Engram/issues/new/choose)**

**Free for personal, noncommercial self-hosting.** Commercial, workplace and
managed-hosting use require separate written permission. Engram is
source-available; see the [license](LICENSE) and [usage guide](docs/LICENSING.md).

## Why Engram?

| When you need to… | Engram gives you… |
| --- | --- |
| Remember the reasoning behind a decision | Source provenance, versioned memories and an event timeline. |
| Bring documents and conversations together | File ingestion, ChatGPT export import and a browser capture extension. |
| Keep extracted facts under your control | A Memory Inbox and human-reviewed agent proposals. |
| Give an AI client useful context | Project-scoped retrieval through MCP and the REST API. |
| Keep personal AI processing on your infrastructure | Local embeddings and extraction through Ollama. |
| Recover your knowledge after a server failure | Encrypted backups and documented, isolated restore testing. |

Built for technically comfortable personal users running Linux and Docker Compose.
The [deployment guide](docs/DEPLOYMENT.md) recommends 4 CPU cores and 8 GB RAM
(16 GB+ preferred), plus storage for your data, models and backups.

Engram 2.8 adds source-cited reflection, reviewed project briefs, memory lifecycle controls, pinning and audited undo. Its shared iOS and Android companion supports project-scoped memories, search, human review and a secure offline library. Native mobile builds remain on their documented preview channel; see [mobile setup](docs/MOBILE.md).

**Current server release:** `v3.0.2`
**Mobile preview:** `v2.7.0-alpha1`
**Recommended deployment:** Linux + Docker Compose + host-managed Cloudflare Tunnel

**v3.0 distribution:** [Native Windows, Linux and macOS setup packages](docs/V3-INSTALLERS.md),
Windows Store packaging and Linux build-provenance verification. Desktop packages
retain the signing and device-qualification limits documented below.

The v2.7.0 release promoted the projects and Memory Agent preview to `main`
and returns to the 2.x release numbering after v6.5.0. It retains the stable
security updates, dependency maintenance and Memory Intelligence features.
See the [changelog](CHANGELOG.md).
The v2.4.0 release added the read-only Gmail connector preview and restored
the Memory Inbox review page; see [Gmail setup](docs/GMAIL.md).

## Highlights

- PostgreSQL + pgvector memory store
- Hybrid semantic + full-text retrieval
- Query planning, graph-aware ranking and source-labelled context previews
- Human-reviewed contradiction resolution that preserves historical facts
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
- OAuth authorization for MCP with PKCE and rotating refresh tokens
- Client ID Metadata Documents and Protected Resource Metadata
- Automated disaster-recovery restore testing
- Backup integrity, retention and off-site replication monitoring
- Administrator observability dashboard for project activity, latency and service readiness
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
git clone https://github.com/Jxyden34/Engram.git
cd Engram

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

v3.0.2 reduces the sidebar to four main sections with related page subtabs inside each one. **Health & about** shows the live server and web versions, service readiness and project memory quality. New installer packages include the Memory Quality fix.

## Native installers — v3.0

The setup wizard bundles prebuilt Engram application images, generates private
configuration and independent secrets, creates your administrator and opens the login
page after checking health. You do not need Python or a local application build.
Docker must already be installed and running; third-party service images and optional
AI models download during setup. Existing installations are preserved.

| Platform | Package | Status |
| --- | --- | --- |
| Windows x64 | ZIP with a compiled setup EXE | Direct download remains unsigned; requires Docker Desktop with Linux containers |
| Windows Store x64 | MSIX plus Store identity metadata | Unsigned submission candidate with a preview identity until Partner Center is configured |
| Linux x64 / ARM64 | Separate tar.gz archives | Signed Sigstore build provenance and verification bundles; requires Docker Engine and Compose 2.24.4+ |
| macOS Intel / Apple Silicon | Separate DMG installers | Unsigned previews; requires Docker Desktop; Apple signing/notarization pending |

Get release packages from [GitHub Releases](https://github.com/Jxyden34/Engram/releases).
Development builds remain available from the **v3 Installer Packages** workflow run
linked from [installer PR #98](https://github.com/Jxyden34/Engram/pull/98). The pipeline exercises
fresh Linux installations, compiles and self-tests five native packages, validates
the MSIX with Microsoft's SDK and verifies Linux provenance. Desktop Docker setup
still needs device qualification; CI checks do not establish Store acceptance.

For Windows Store distribution, register a free individual developer account and
provide Partner Center's three identity values. Microsoft signs accepted Store
submissions; the direct-download EXE remains unsigned. On Linux, download the archive
and matching `.sigstore.json` bundle and follow the recorded GitHub CLI verification
command before running the installer.

See the [installer guide](docs/V3-INSTALLERS.md) for requirements, Store variables,
Linux verification and the Ubuntu/Debian one-line bootstrap. A matching v3 tag attaches
the packages, checksums and Linux provenance to a draft GitHub release for review
before publication. New Linux hosts can use:

```sh
curl -fsSL https://raw.githubusercontent.com/Jxyden34/Engram/main/install.sh | sudo bash
```

This permanent top-level launcher selects the latest stable package automatically;
the command does not change for each release. A deployed instance can also serve it
at `/install.sh`. Use `ENGRAM_INSTALL_VERSION` only when deliberately pinning a release.
This requires an interactive terminal and a published package. Existing deployments
must follow the [upgrade guide](docs/UPGRADING.md), not the fresh-install wizard.

## Cloudflare Tunnel

Engram intentionally does **not** include a `cloudflared` container.

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
- [Native installers, Windows Store setup and Linux verification](docs/V3-INSTALLERS.md)
- [Upgrading](docs/UPGRADING.md)
- [Backup and restore](docs/BACKUP-RESTORE.md)
- [Operations](docs/OPERATIONS.md)
- [Roadmap](docs/ROADMAP.md)
- [Projects and Memory Agent beta](docs/PROJECTS-AGENT.md)
- [Portfolio & engineering evidence](docs/PORTFOLIO.md)
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

Engram is **source-available and free for personal, noncommercial self-hosting**.
Commercial, workplace and managed-hosting use require separate written permission.
See [LICENSE](LICENSE) and the [usage guide](docs/LICENSING.md).
