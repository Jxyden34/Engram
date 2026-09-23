# Security Policy

Engram stores highly sensitive personal information and should be treated like private-cloud infrastructure.

## Reporting a vulnerability

If this repository is hosted on GitHub, use **GitHub Private Vulnerability Reporting / Security Advisories** rather than opening a public issue containing exploit details.

## Never expose directly

Do not router-forward or publish these services:

- PostgreSQL `5432`
- Redis `6379`
- Ollama `11434`
- MinIO `9000` / `9001`
- FastAPI `8000`
- Next.js `3000`

Only the local Caddy gateway on `127.0.0.1:8080` should be reached by the host-managed Cloudflare Tunnel.

## Secrets

Never commit `.env`.

Use independent random secrets for:

- PostgreSQL
- Redis
- MinIO
- backup encryption
- API credentials

Rotate any credential that appears in:

- Git history
- screenshots
- public issues
- CI logs
- chat transcripts
- shell history shared publicly

## AI permissions

Ordinary AI agents should use the minimum scopes they need. Do not give automated clients deletion approval or key administration unless absolutely necessary.

## Backups

Backups contain the same sensitive information as production.

- encrypt backups
- retain an off-host copy
- test restores
- protect backup encryption keys separately
