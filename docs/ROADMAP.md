# Engram Roadmap

> A self-hosted personal memory, knowledge and AI context platform.

This roadmap tracks the evolution of Engram from a secure personal memory store into a full personal knowledge operating system.

---

## Status legend

- ✅ Shipped
- 🟢 Current
- 🟡 Planned
- 🔵 Later
- 🧪 Experimental

## Alpha1 — mobile review and filtered Ask 🧪

These features are implemented in PR #36 on `codex/projects-memory-agent`; device qualification is in progress. Beta4 remains available at commit `9f34cd1` and Android build 6 for rollback:

- **Ask filters:** choose memory type and a date range before retrieval. Apply filters on the server inside the active project's RLS scope; display the filters used with each answer. Keep Ollama as the answer provider and preserve checked source quotations.
- **Suggested memory connections:** propose related memories within the active project, show both sources and the reason, and create a link only after explicit approval. Exclude deleted memories and existing links; reject links across projects.
- **Richer mobile Agent review:** approve or dismiss findings, edit proposed memory text before saving, check for stale sources, and record the human action. Keep source memories unchanged unless a separate explicit action permits an edit.

Before qualifying Alpha1, validate populated findings/links, stale-source handling, project isolation, retries and review actions on both physical devices. The version is `2.7.0-alpha1` and the separate update channel is `alpha1`; keep beta4 available for rollback.

---

## Active release tracks

Engram is developed on two deliberately separate tracks. Stable releases do not
absorb unfinished preview work.

| Track | Current position | Scope |
| --- | --- | --- |
| Stable | **v2.5.5 shipped** | Production self-hosted releases. v2.5.5 delivers Memory Intelligence without projects, mobile beta work or the Memory Agent from the preview track. |
| Preview | **v2.7.0-alpha1 in development** | Projects, mobile companion and human-reviewed Agent proposals. It remains a pre-release until project isolation, mobile flows and release qualification are complete. |

v2.5.5 is the current GitHub stable release and is deployed on Blackwall. It
includes explainable retrieval, compact context and reviewed contradiction
resolution. The v2.4.5 S3-compatible storage change remains part of stable.

---

# v1 — Foundation

## v1.0 — Core Memory Platform ✅

Core platform and security model.

### Shipped

- PostgreSQL + pgvector as the source of truth
- FastAPI backend
- Next.js web interface
- Redis + RQ background jobs
- MinIO source document storage
- Ollama local AI
- `all-minilm` embeddings
- REST API
- MCP endpoint
- Browser authentication
- API keys with scoped permissions
- Audit logging
- Soft-delete approval workflow
- Encrypted backups
- Caddy local gateway
- Host-managed Cloudflare Tunnel
- Internal Docker network isolation

## v1.1 — Bulk Ingestion ✅

- Multi-file uploads
- Folder uploads
- ZIP ingestion
- ZIP path traversal protection
- ZIP symlink rejection
- Compression-ratio safety checks
- Expanded-size limits
- Duplicate detection using SHA-256
- PDF, DOCX, TXT, Markdown, CSV, JSON, YAML and log support

## v1.2 — ChatGPT Importer ✅

- ChatGPT export ingestion
- `conversations.json` support
- Conversation parsing
- Candidate memory extraction
- Local Qwen analysis
- Confidence scoring
- Existing-memory comparison
- `new`, `duplicate`, `related`, `updates`, `conflicts`
- Conversation provenance
- Candidate review interface
- Safe bulk acceptance

## v1.3 — Document Memory Extraction ✅

- Candidate memory extraction from uploaded documents
- Document chunk analysis
- Source excerpts
- Provenance tracking
- Candidate acceptance workflow

## v1.4 — Unified Memory Inbox ✅

- One Memory Inbox for all candidate memories
- ChatGPT candidates
- Document candidates
- Unified filtering and acceptance
- `Analyse everything`
- Automatic duplicate/update/conflict checks

---

# v2 — Knowledge Operating System

## v2.0 — Knowledge Core ✅

### Entity Graph

- Entity extraction
- Entity storage
- Entity relationships
- Entity-to-memory linking
- Graph API
- Knowledge Graph UI

### Temporal Memories

- `valid_from`
- `valid_to`
- superseding memories
- preserved historical facts
- current-fact resolution

### Memory Importance

Dynamic score based on:

- explicit importance
- confidence
- source trust
- age
- retrieval frequency
- recency
- relationship density

### Event Timeline

- Date-aware memories
- Extracted events
- Chronological timeline
- Event provenance

### Memory Health

- duplicate detection
- conflict detection
- stale facts
- low-confidence memories
- orphan memories
- missing provenance
- health summary dashboard

---

## v2.1 — Ingestion Mesh ✅

Continuous ingestion from external systems.

### Connector Framework ✅

- Connector database model
- Scheduled sync service
- Sync history
- Connector status
- Source hashing
- Change detection
- Source provenance
- Unified Memory Inbox integration

### GitHub Connector ✅

Uses a GitHub App instead of a personal access token.

Supported ingestion:

- Repository metadata
- README files
- Documentation
- Issues
- Pull requests
- Source code optionally

Remaining GitHub work:

- 🟡 Webhook-triggered instant sync
- 🟡 Commit ingestion
- 🟡 Release ingestion
- 🟡 Discussions
- 🟡 Repository branch selection
- 🟡 Per-repository filters
- 🟡 Ignore patterns
- 🟡 Source-code language filters
- 🟡 Connector health diagnostics

### Browser Capture ✅

Chrome / Edge Manifest V3 extension.

Supported:

- Capture page
- Capture selected text
- Capture links
- Quick notes
- Right-click capture menu
- Dedicated `capture:write` API scope
- Source provenance
- Automatic candidate-memory analysis

Planned:

- 🟡 Reader-mode extraction
- 🟡 Screenshot capture
- 🟡 Image OCR
- 🟡 Capture tags
- 🟡 Project / namespace selection
- 🟡 Mobile share-sheet support
- 🟡 Firefox extension

---

## v2.2 — Identity & MCP ✅

Modernize how external AI tools authenticate to Engram.

**Status:** Shipped in v2.2.0 with PKCE, protected-resource discovery, CIMD, rotating refresh tokens, resource-bound access tokens, consent and client/grant revocation.

### OAuth / OIDC

- OAuth 2.1
- OIDC support
- PKCE
- short-lived access tokens
- refresh tokens
- client registration
- token revocation
- per-client scopes
- per-client audit trail

### MCP Authorization

Example scopes:

```text
memory:read
memory:write
memory:delete_request
document:read
capture:write
mcp:use
```

### Client Management UI

- authorized clients
- granted scopes
- last-used timestamp
- revoke client
- rotate credentials
- access history

---

## v2.3 — Disaster Recovery ✅

### Backup Dashboard

Show:

- latest PostgreSQL backup
- latest MinIO backup
- backup sizes
- backup duration
- encryption status
- retention status
- off-site copy status
- last restore test

### Automated Restore Testing

Regularly:

1. create isolated restore environment
2. restore PostgreSQL
3. validate schema
4. validate row counts
5. verify pgvector
6. verify source-object references
7. destroy test environment
8. publish result to dashboard

### Backup Replication

Targets:

- secondary Linux host
- NAS
- encrypted cloud object storage
- off-site server

### Recovery Documentation

Cover:

- database loss
- MinIO loss
- full-host loss
- accidental deletion
- broken migration
- corrupted Docker volume

---

## v2.4 — Expanded Connectors ✅

Start with the read-only Gmail connector. Keep later sources out of the first
release until sync, credential storage and source deletion behavior are proven.
The initial Gmail scope imports selected mail as source documents and candidate
memories; it does not send, modify, delete messages or import attachments.

### Email

Potential sources:

- Gmail
- Microsoft 365

Ingest:

- selected mailboxes
- starred messages
- labels/folders
- attachments
- important threads

#### First release: Gmail

- 🟡 OAuth authorization with `gmail.readonly` only.
- 🟡 User-selected Gmail query, label and sync limit.
- 🟡 Scheduled bounded-query sync with idempotent document updates.
- 🟡 Each run reads up to 500 newest matches; historical cursor/backfill remains future work.
- 🟡 Encrypted refresh-token storage and account disconnect / revocation.
- 🟡 Message provenance, search indexing and candidate-memory review.
- 🟡 No compose, send, modify, delete, attachment or mailbox-wide default sync.

### Calendar

Potential sources:

- Google Calendar
- Microsoft 365

Extract:

- meetings
- appointments
- attendees
- locations
- recurring events
- event notes

### Cloud Storage

Potential sources:

- Google Drive
- OneDrive
- SharePoint
- Dropbox

Features:

- folder selection
- incremental sync
- file version detection
- deleted-source handling
- provenance preservation

### Notes / Knowledge Systems

Potential connectors:

- Notion
- Obsidian
- OneNote
- Markdown repositories

---

## v2.5 — Memory Intelligence ✅

**Stable milestone:** v2.5.5 is separate from the v2.7 preview line.

### Hybrid Retrieval

Combine:

- vector similarity
- PostgreSQL full-text search
- entity relationships
- temporal relevance
- memory importance
- source trust
- recency
- retrieval history
- explain why a result ranked highly

### Query Planner

Classify incoming questions before retrieval.

### Context Builder

Build compact, high-quality AI context automatically.

Goals:

- reduce irrelevant memories
- reduce token usage
- preserve provenance
- prioritize current facts
- include useful history when needed
- provide a bounded context preview before an AI client uses it

### Contradiction Resolution

Compare:

- confidence
- date
- provenance
- source authority

Nothing should be silently deleted.

Shipped in v2.5.5: the Intelligence page exposes a bounded context preview,
retrieval explanations, similar-pair review and an explicit resolution action.
Choosing a current fact retains the other as historical and records its previous
version, provenance and the resolution decision. This release does not include
Projects, the memory agent, Ask Engram or mobile features planned separately
for v2.7.

---

## v2.6 — Personal Search Engine 🔵

One search interface across:

- memories
- documents
- browser captures
- GitHub
- ChatGPT history
- events
- entities
- source excerpts

Filters:

- source
- date
- entity
- importance
- project
- content type
- confidence

Search results should explain why they matched.

---

## v2.7 — Projects, Mobile & Proposal Agent 🟢

**Preview milestone:** `v2.7.0-dev` is the separate pre-release line. It is
not part of v2.5.5 or any other stable release until its qualification gates
are met.

Examples:

- Personal
- Work
- Engram
- Home Lab
- Cosmopod
- Career
- Travel

Features:

- ✅ namespace-specific memories and project switching
- ✅ project context propagated through the API and MCP
- ✅ project-scoped connector and candidate-memory boundaries
- 🟡 project-specific API keys and retention
- 🟡 explicit, auditable cross-project search
- 🟡 isolation testing across memory, document, connector, OAuth callback and
  import paths

### Mobile companion preview

- ✅ capture templates, memory creation, search, Ask with source links and
  project switching tested online on iPhone through Expo Go
- ✅ native sharing, Agent scan completion, and empty history/connection states
  tested online
- 🟡 favourites and offline access in a standalone signed build
- 🟡 populated version-history and connection navigation
- 🟡 beta4 voice capture with transcript review (requires a rebuilt native app;
  keyboard dictation remains the Expo Go fallback)
- 🟡 beta4 device-local Inbox for rough captures before organising them

### Memory Agent preview

The Agent remains proposal-only: it must not silently rewrite memories or cross
project boundaries.

- ✅ scan and proposal workflow
- 🟡 alpha1 Ask filters for source, memory type and date range
- 🟡 alpha1 suggested memory links with explicit approval
- 🟡 alpha1 mobile review, edit, approve and dismiss flow for Agent proposals

---

## v2.8 — Memory Lifecycle 🔵

### Decay

Reduce retrieval priority for memories that are:

- never retrieved
- low confidence
- low importance
- outdated
- superseded
- weakly sourced

### Consolidation

Merge repetitive memory clusters into stronger summaries while keeping originals traceable.

### Archival

Move cold memories into archival state while keeping them searchable.

---

## v2.9 — Observability 🔵

Metrics for:

- API latency
- ingestion rate
- queue depth
- failed jobs
- embedding latency
- Qwen processing time
- PostgreSQL health
- MinIO health
- Redis health
- connector sync status
- candidate acceptance rate

Potential integrations:

- Prometheus
- Grafana
- alerting
- health notifications

---

## v2.10 — Managed Service Readiness 🔵

Prepare a managed Engram offering without weakening the self-hosted product or
promising enterprise operations before they are proven.

### Activation and product operations

- guided first-run path to capture or import, then retrieve, a first memory
- visible usage for memories, documents, storage, connectors and backup status
- documented managed-hosting boundaries for upgrades, backups, recovery and
  support
- privacy-respecting activation measurement: first captured or imported memory
  successfully retrieved

### Team and deployment foundations

- multi-user membership and project roles
- advanced RBAC and shared MCP/API governance
- SSO / SCIM only after team administration is proven
- managed deployment provisioning, upgrades, backup verification and recovery
  runbooks
- quota, retention and support controls before any paid plan is offered

### Validation gate

Before billing or a public managed launch: validate willingness to pay with
customer interviews, demonstrate a repeatable recovery, and define the actual
uptime, support and data-handling commitments. This is a readiness milestone,
not a promise of a hosted service date.

---

# v3 — Personal Knowledge OS 🔵

## v3.0 — Memory Agent

A controlled autonomous maintenance agent.

Responsibilities:

- detect duplicates
- identify conflicts
- discover stale memories
- suggest consolidation
- propose entity relationships
- improve provenance
- suggest missing facts

The agent proposes changes. It does not silently rewrite personal history.

## v3.1 — Personal API Gateway

Unified permission layer for:

- ChatGPT
- local LLMs
- scripts
- home automation
- mobile apps
- developer tools
- dashboards

## v3.2 — Notifications

Notify on:

- connector failure
- important memory conflict
- backup failure
- meaningful updates to important facts
- stale credential documentation
- unresolved candidate memories

## v3.3 — Mobile Companion Expansion

Potential capabilities:

- standalone signed mobile builds and offline favourites
- quick capture and voice notes beyond the v2.7 preview
- photos
- share-sheet ingestion
- search
- timeline
- approvals
- notifications

## v3.4 — Multimodal Memory

Support:

- images
- screenshots
- audio
- video
- scanned documents

## v3.5 — Personal Knowledge Graph Explorer

Features:

- entity clusters
- timeline overlay
- relationship confidence
- source drill-down
- memory history
- conflict visualization
- project boundaries

---

# Principles

1. PostgreSQL remains the source of truth.
2. Preserve provenance.
3. Never silently rewrite history.
4. AI proposes, humans control.
5. Local AI first.
6. Least privilege everywhere.
7. Sources are not automatically permanent memories.
8. Backups must be tested by restoring them.
9. Avoid vendor lock-in.
10. Security beats convenience.

---

# Immediate Priorities

1. ✅ Complete and qualify stable v2.5.5 Memory Intelligence.
2. 🟢 Complete v2.7 beta4 voice capture and device-local Inbox without merging
   preview work into the stable track.
3. 🟡 Qualify v2.7 project isolation, mobile flows and proposal-only Agent
   boundaries; then sequence alpha1 Ask filters, memory links and Agent review.
4. 🟡 GitHub webhook-triggered sync, commit/release ingestion and connector
   diagnostics.
5. 🟡 Disaster Recovery dashboard, automated restore testing and backup
   replication.
6. 🟡 Gmail read-only connector qualification, then calendar and cloud-storage
   connectors.
7. 🟡 Universal search and the explicit cross-project search/audit model.
8. 🔵 Memory consolidation, decay and archival.
9. 🔵 Managed-service readiness: onboarding, usage visibility, team governance
   and operational commitments.
10. 🔵 v3 autonomous maintenance and notification capabilities.

---

# North Star

Engram should eventually answer:

> **What do I know, where did I learn it, when was it true, how confident am I, what has changed, and which parts are relevant right now?**

Without handing ownership of that knowledge to someone else's cloud.
