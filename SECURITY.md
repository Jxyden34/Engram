# Security notes

This repository contains personal-data infrastructure. Treat it like a password manager or private cloud.

## Never expose directly

Do not publish or router-forward:

- PostgreSQL 5432
- Redis 6379
- Ollama 11434
- MinIO 9000 / 9001
- FastAPI 8000

Cloudflare Tunnel should point only to `gateway:8080`.

## Secrets

Keep `.env` out of Git.

Use independent, randomly generated credentials for PostgreSQL, Redis, MinIO and backup encryption.

API tokens are displayed once. Revoke a token immediately if it is pasted into logs, screenshots, tickets or public chat.

## AI permissions

For ordinary AI agents, use:

- memory:read
- memory:write
- memory:delete_request
- document:read
- mcp:use

Do not grant `memory:delete_approve` or `keys:admin`.

## Cloudflare

Recommended production controls:

- WAF managed rules
- rate limiting on `/api/v1/auth/login`
- Bot protection if available
- force HTTPS
- do not cache `/api/*` or `/mcp`
- keep Cloudflare Tunnel token secret

## Backups

Backups contain the same sensitive data as production.

The included backup jobs encrypt local copies, but move encrypted backups to a second physical machine or storage provider as well.

Test restores periodically.
