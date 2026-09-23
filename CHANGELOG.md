# Changelog

## 2.7.0-dev-beta.1 - unreleased

- Add project selection and project-bound API keys. Existing records migrate to Personal.
- Enforce project boundaries on memory, document, import, graph and connector tables with PostgreSQL row-level security.
- Carry project context into queued ingestion and enrichment jobs.
- Add a read-only memory agent that proposes reviews for duplicates, conflicts, stale facts and missing provenance; it never edits memories.
- This is a development beta. Apply migration 009 before starting the updated API and workers.

## 2.4.0 - 2026-09-23

### Added

- Gmail read-only connector preview using the existing scheduled connector flow.
- OAuth state bound to the active administrator session, with one-use expiry.
- Public About, Privacy and Terms pages for OAuth app verification.
- Encrypted Google refresh tokens, explicit disconnect/revocation, selectable
  Gmail query/label, bounded message polling and provenance-preserving source
  documents routed through the Memory Inbox review workflow.
- Restored the Memory Inbox page used to review imported content.
- Google setup, restricted-scope and migration notes in `docs/GMAIL.md`.

### Scope

- Gmail API `gmail.readonly` only: no sending, modifying, deleting or attachments.
- Gmail setup requires Google OAuth project configuration and migration 008 on
  existing installations.
- Each Gmail run is capped to the newest 500 matching messages; historical
  backfill beyond that cap is not supported in this preview.

## 2.3.1 DR polish - 2026-09-18

This source update retains version 2.3.1 and all existing v2.3 APIs and database
tables. The published v2.3.1 tag is unchanged.

- Process manual DR requests before background scans and again after scans.
- Cache successful archive verification for at most 24 hours using device, inode,
  size, nanosecond mtime and ctime, and confirm the database still holds the verified
  digest. Manual scans always force full SHA-256, decrypt and archive checks.
- Verify only selected backups for manual restore/replicate requests. On a cold
  inventory, discover the newest candidate of each type without scanning history.
- Replicate selected backups manually and all inventoried verified backups on
  automatic runs, preserving encrypted-only Blackwall-to-DarkMatter copy behavior.
- Record actual rclone transfer counters and UTC operational logs, including
  cache hits, verification failures, queue outcomes and operation durations.
- Publish encrypted backups through an atomic `.partial` rename.
- Add isolated PostgreSQL/rclone regression checks to CI and enforce LF for shell
  scripts. No migration or new deployment environment variables are required.

See [upgrade notes](UPGRADE-v2.3.1-DR-POLISH.md) for deployment and verification.

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
