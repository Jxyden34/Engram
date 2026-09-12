# MemoryBank Roadmap

> A self-hosted personal memory, knowledge and AI context platform.

This roadmap tracks the evolution of MemoryBank from a secure personal memory store into a full personal knowledge operating system.

---

## Status legend

- ✅ Shipped
- 🟢 Current
- 🟡 Planned
- 🔵 Later
- 🧪 Experimental

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

## v2.1 — Ingestion Mesh 🟢

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

Modernize how external AI tools authenticate to MemoryBank.

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

## v2.4 — Expanded Connectors 🟡

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

## v2.5 — Memory Intelligence 🟡

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

### Contradiction Resolution

Compare:

- confidence
- date
- provenance
- source authority

Nothing should be silently deleted.

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

## v2.7 — Projects & Namespaces 🔵

Examples:

- Personal
- Work
- MemoryBank
- Home Lab
- Cosmopod
- Career
- Travel

Features:

- namespace-specific memories
- per-project connectors
- project-specific API keys
- MCP project context
- project-specific retention
- explicit cross-project search

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

## v3.3 — Mobile Companion

Potential capabilities:

- quick capture
- voice notes
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

1. ✅ v2.1 GitHub connector
2. ✅ Browser Capture
3. 🟡 GitHub webhook-triggered sync
4. ✅ v2.2 OAuth / MCP authorization
5. 🟡 v2.3 Disaster Recovery dashboard
6. 🟡 Email and calendar connectors
7. 🟡 Improved hybrid retrieval
8. 🔵 Projects / namespaces
9. 🔵 Memory consolidation and decay
10. 🔵 v3 Memory Agent

---

# North Star

MemoryBank should eventually answer:

> **What do I know, where did I learn it, when was it true, how confident am I, what has changed, and which parts are relevant right now?**

Without handing ownership of that knowledge to someone else's cloud.
