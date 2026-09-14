# MemoryBank Deployment

This guide covers deployment of MemoryBank v2.3.1 on a Linux host using Docker Compose.

---

## Recommended host

Recommended baseline:

```text
Ubuntu Server 24.04 LTS or newer
4 CPU cores minimum
8 GB RAM minimum
16 GB+ recommended
Docker Engine
Docker Compose plugin
```

Additional storage requirements depend on:

- PostgreSQL data
- Ollama models
- uploaded documents
- MinIO objects
- backups

---

## Repository

Clone the repository:

```bash
git clone https://github.com/Jxyden34/Memory-Bank.git
cd Memory-Bank
```

---

## Environment configuration

Copy the example file:

```bash
cp .env.example .env
```

Edit:

```bash
nano .env
```

Generate strong random secrets:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
```

Use independent values for services such as:

- PostgreSQL
- Redis
- MinIO
- backup encryption

Never commit `.env`.

---

## Start the stack

```bash
sudo docker compose up -d --build
```

Check container status:

```bash
sudo docker compose ps
```

---

## Pull Ollama models

```bash
sudo docker compose exec ollama ollama pull all-minilm
sudo docker compose exec ollama ollama pull qwen3:4b
```

Verify:

```bash
sudo docker compose exec ollama ollama list
```

---

## Create an administrator

```bash
sudo docker compose exec -it api python scripts/create_admin.py
```

Follow the prompts.

---

## Local health check

```bash
curl http://127.0.0.1:8080/health
```

Expected result should indicate that MemoryBank is healthy.

---

## Cloudflare Tunnel

MemoryBank expects `cloudflared` to run on the host.

The Compose stack does not manage the Cloudflare Tunnel container.

Configure your public hostname to forward to:

```text
http://127.0.0.1:8080
```

Check the host service:

```bash
sudo systemctl status cloudflared
```

Restart if required:

```bash
sudo systemctl restart cloudflared
```

---

## GitHub connector configuration

MemoryBank v2.3.1 supports a GitHub App.

Recommended read-only repository permissions:

```text
Metadata
Contents
Issues
Pull requests
```

Generate a GitHub App private key.

Create the local secrets directory:

```bash
mkdir -p secrets
chmod 700 secrets
```

Place the key at:

```text
secrets/github-app.pem
```

Protect it:

```bash
chmod 600 secrets/github-app.pem
```

Set the App ID in `.env`:

```dotenv
GITHUB_APP_ID=YOUR_APP_ID
GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/github-app.pem
```

Recreate the required services:

```bash
sudo docker compose up -d --force-recreate api worker connector-scheduler
```

Open:

```text
/connectors
```

and configure the installation ID and repositories.

---

## Browser Capture extension

The extension source is located at:

```text
extensions/memorybank-capture
```

In Chrome:

```text
chrome://extensions
```

In Edge:

```text
edge://extensions
```

Enable Developer mode and choose:

```text
Load unpacked
```

Select the extension directory.

In MemoryBank, generate a dedicated Browser Capture key.

The key should use only:

```text
capture:write
```

Configure the extension with:

```text
https://YOUR-MEMORYBANK-HOST
```

and the generated capture key.

---

## Verify services

```bash
sudo docker compose ps
```

Useful logs:

```bash
sudo docker compose logs api --tail=100
sudo docker compose logs worker --tail=100
sudo docker compose logs web --tail=100
sudo docker compose logs connector-scheduler --tail=100
```

---

## Firewall

Do not expose application service ports directly.

Public ingress should arrive through Cloudflare Tunnel.

Internal service ports such as these should not be router-forwarded:

```text
5432
6379
9000
9001
11434
3000
8000
```

---

## Deployment checklist

Before considering deployment complete:

- containers are healthy
- models are installed
- admin account exists
- `/health` succeeds
- Cloudflare Tunnel works
- `.env` is not tracked by Git
- secrets directory is protected
- PostgreSQL backup has been tested
- MinIO backup exists
- browser/API keys use least privilege


## OAuth / MCP settings

Recommended defaults:

```dotenv
OAUTH_ACCESS_TOKEN_MINUTES=15
OAUTH_REFRESH_TOKEN_DAYS=30
OAUTH_AUTHORIZATION_CODE_MINUTES=5
OAUTH_CIMD_TIMEOUT_SECONDS=5
OAUTH_CIMD_MAX_KB=256
OAUTH_DCR_ENABLED=true
```

Verify discovery after deployment:

```bash
curl -s https://YOUR-HOST/.well-known/oauth-protected-resource/mcp
curl -s https://YOUR-HOST/.well-known/oauth-authorization-server
```

## Validated clean deployment

MemoryBank v2.3.1 was validated from a clean repository clone on a separate Linux host.

The clean deployment verified:

- Docker Compose configuration
- PostgreSQL initialization from the tracked bootstrap schema
- pgvector availability
- Redis connectivity
- MinIO initialization
- FastAPI health checks
- Next.js web startup
- background worker startup
- encrypted PostgreSQL backups
- encrypted object backups
- successful handling of an empty MinIO bucket
- HTTP 200 health response through the Caddy gateway

The validation also identified and fixed:

1. unavailable legacy Docker Hub MinIO references
2. object-backup failure when the MinIO bucket contained zero objects

Fresh deployments should use the immutable image references committed in
`docker-compose.yml`.

If port 8080 is already occupied on a recovery or test host, use a local Docker
Compose override to publish the gateway on another loopback port rather than
modifying the production Compose definition.
