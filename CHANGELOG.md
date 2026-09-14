# Changelog

## 2.3.1 - 2026-09-14

### Added

- Backend schema unit tests.
- PostgreSQL + pgvector integration testing in GitHub Actions.
- Redis connectivity and round-trip integration testing.
- Deterministic frontend dependency installation using `package-lock.json` and `npm ci`.
- CI validation that externally hosted production images remain pullable.

### Changed

- Production container images are pinned to immutable digests.
- MinIO Community images use working Quay registry references.
- CI uses the Python 3.14 production runtime.
- Dependabot patch and minor updates can auto-merge after required CI checks.
- Docker and Docker Compose dependency changes remain manual.
- Main branch requires backend, web and Docker CI checks.

### Fixed

- Fresh deployments no longer depend on previously cached MinIO images.
- Empty MinIO buckets now produce valid encrypted object backups.
- PostgreSQL bootstrap schema is tracked for repeatable deployments.

### Validation

- Clean deployment successfully tested on a separate Linux host.
- MemoryBank health endpoint returned HTTP 200 through Caddy.
- Real off-site encrypted backups successfully restored on a separate recovery host.
- 672 memories restored.
- 422 documents restored.
- 422 object files restored.
- Zero missing object references.
- pgvector successfully validated after restore.
- Full isolated recovery completed in 17 seconds.


## 2.3.0 - 2026-09-12

### Added

- Disaster Recovery dashboard and resilience score.
- Encrypted PostgreSQL and object backup artifact inventory.
- SHA-256 and decrypt/integrity verification.
- Automated isolated PostgreSQL restore tests.
- pgvector validation and restored row counts.
- MinIO archive extraction and document-object reference checks.
- Backup filesystem capacity monitoring.
- Optional encrypted off-site replication via rclone.
- Manual verify, restore-test and replication actions.


## 2.2.0 - 2026-09-12

### Added

- OAuth authorization code flow for MCP clients.
- Mandatory PKCE S256.
- Short-lived access tokens and rotating refresh tokens.
- Refresh-token reuse detection and family revocation.
- OAuth Protected Resource Metadata and Authorization Server Metadata.
- Client ID Metadata Document support.
- Pre-registered clients and legacy Dynamic Client Registration fallback.
- Resource-bound MCP tokens and issuer-aware authorization responses.
- OAuth client / grant management in AI & API settings.


## 2.1.0 - 2026-09-11

### Added

- Connector framework and scheduled sync service.
- GitHub App repository, README, docs, issues and pull-request ingestion.
- Optional GitHub source-code ingestion.
- Browser Capture endpoint and Chrome/Edge extension.
- `capture:write` and `connector:admin` scopes.
- Document source provenance and automatic connector/capture candidate analysis.


## 2.0.1 - 2026-09-11

### Fixed

- Next.js production build issue in Timeline and Memory Health pages.

## 2.0.0 - 2026-09-11

### Added

- Entity graph and entity relationships.
- Temporal validity and superseding memories.
- Dynamic memory scoring.
- Event timeline.
- Memory health dashboard.
- Background knowledge enrichment.

## 1.4.0

- Unified ChatGPT and document candidate Memory Inbox.
- One `Analyse everything` workflow.

## 1.3.0

- Generic document-to-memory candidate extraction.

## 1.2.0

- ChatGPT conversation export importer.
- Candidate memory review and provenance.

## 1.1.0

- Bulk file, folder and ZIP ingestion.

## 1.0.0

- Initial MemoryBank full-stack platform.
