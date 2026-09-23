# Engram v2.2 — Identity & MCP

v2.2 replaces "paste a permanent API key into every AI client" with a proper OAuth authorization layer.

## Features

- OAuth authorization code flow
- PKCE S256
- Client ID Metadata Documents
- Protected Resource Metadata
- Authorization Server Metadata
- pre-registered clients
- Dynamic Client Registration compatibility fallback
- 15-minute access tokens by default
- rotating refresh tokens
- token family reuse detection
- resource-bound MCP tokens
- RFC 9207-style `iss` on authorization responses
- consent page
- OAuth client dashboard
- grant revocation
- legacy API-key compatibility
- current MCP v2 SDK remains compatible with 2026-07-28 clients

## 1. Back up PostgreSQL

```bash
cd /opt/memorybank/memorybank

sudo docker compose exec db sh -lc \
  'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/memorybank-pre-v2.2.dump'

sudo docker compose exec db \
  pg_restore --list /tmp/memorybank-pre-v2.2.dump | head -30
```

## 2. Pause workers

```bash
sudo docker compose stop worker connector-scheduler
```

## 3. Extract patch

```bash
cd /opt/memorybank

sudo unzip -o \
  /home/jayden/memorybank-v2.2-identity-mcp-patch.zip \
  -d /opt/memorybank

cd /opt/memorybank/memorybank
```

## 4. Apply migration 006

```bash
sudo docker compose exec -T db sh -lc \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/migrations/006_identity_mcp.sql
```

## 5. Add OAuth settings

Append to `.env` if not already present:

```dotenv
OAUTH_ACCESS_TOKEN_MINUTES=15
OAUTH_REFRESH_TOKEN_DAYS=30
OAUTH_AUTHORIZATION_CODE_MINUTES=5
OAUTH_CIMD_TIMEOUT_SECONDS=5
OAUTH_CIMD_MAX_KB=256
OAUTH_DCR_ENABLED=true
```

## 6. Rebuild

```bash
sudo docker compose build --no-cache api worker web connector-scheduler
```

## 7. Start v2.2

```bash
sudo docker compose up -d \
  --force-recreate \
  api worker web gateway connector-scheduler
```

## 8. Verify containers

```bash
sudo docker compose ps
```

## 9. Verify OAuth metadata

Replace the public hostname below:

```bash
curl -s https://YOUR-HOST/.well-known/oauth-protected-resource/mcp
```

and:

```bash
curl -s https://YOUR-HOST/.well-known/oauth-authorization-server
```

## 10. Verify MCP challenge

```bash
curl -i https://YOUR-HOST/mcp
```

The response should include a `WWW-Authenticate` header containing:

```text
resource_metadata="https://YOUR-HOST/.well-known/oauth-protected-resource/mcp"
```

## 11. Dashboard

Hard refresh the site:

```text
Ctrl + F5
```

Open:

```text
AI, API & OAuth
```

You should now see:

- OAuth metadata
- OAuth clients
- authorization grants
- token counts
- pre-registration form
- grant/client revoke controls

## Rollback

The old `mem_live_...` API-key flow is retained, so existing clients continue to work after the upgrade.

If the application layer must be rolled back, restore the v2.1 code. Migration 006 is additive and does not alter existing API-key tables.
