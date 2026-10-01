# Engram Architecture

Engram is a self-hosted personal memory, knowledge and AI context platform.

The architecture is designed around four principles:

1. PostgreSQL is the source of truth.
2. AI-derived data must remain traceable to its source.
3. External clients receive only the permissions they need.
4. Public exposure is limited to the application gateway.

---

## High-level architecture

```text
                        Internet
                           |
                    Cloudflare HTTPS
                           |
                host-managed cloudflared
                           |
                    127.0.0.1:8080
                           |
                     Caddy Gateway
                    /             \
                   /               \
            Next.js Web          FastAPI API
                                    |
              +---------------------+---------------------+
              |            |             |                |
         PostgreSQL       Redis         Ollama           MinIO
         + pgvector        RQ       embeddings/Qwen    documents
              |
              +---- entities
              +---- memories
              +---- timeline
              +---- candidate memories
              +---- connector state
```

---

## Components

### Next.js Web

Provides the authenticated management interface for:

- memories
- documents
- Memory Inbox
- Knowledge Graph
- Timeline
- Memory Health
- connectors
- approvals
- audit logs
- API credentials

The web app is not exposed directly. Requests arrive through Caddy.

---

## FastAPI

The API service owns the main application logic.

Responsibilities include:

- authentication
- sessions
- API keys
- REST endpoints
- MCP endpoints
- document ingestion
- browser capture
- ChatGPT import
- candidate memory processing
- memory lifecycle
- approvals
- audit logging
- entity graph
- timeline
- connector administration

---

## PostgreSQL + pgvector

PostgreSQL is the canonical source of truth.

Stored data includes:

- users
- sessions
- API keys
- memories
- memory versions
- deletion requests
- audit records
- documents
- document chunks
- candidate memories
- ChatGPT import jobs
- connectors
- connector items
- sync runs
- entities
- entity relationships
- timeline events
- embeddings

pgvector is used for semantic search and nearest-memory comparison.

Derived data should always be rebuildable from the database and source objects.

---

## Redis + RQ

Redis provides the queue backend for asynchronous work.

RQ workers handle tasks such as:

- document extraction
- chunking
- embeddings
- candidate memory extraction
- connector ingestion
- knowledge enrichment

A dedicated connector scheduler periodically checks for due connector jobs.

---

## Ollama

Ollama provides local AI processing.

Current models:

```text
all-minilm
qwen3:4b
```

### all-minilm

Used for embeddings.

Current embedding dimension:

```text
384
```

### qwen3:4b

Used for structured local analysis such as:

- memory extraction
- duplicate detection
- update detection
- conflict detection
- entity extraction
- relationship extraction
- event extraction

Ollama joins the internal backend network and a separate egress network so models can be downloaded without exposing Ollama publicly.

---

## MinIO

MinIO stores source files uploaded or created by Engram.

Examples:

- PDFs
- DOCX files
- text files
- ZIP-imported files
- browser captures
- GitHub connector source documents
- ChatGPT exports

PostgreSQL stores metadata and object references.

MinIO is not publicly exposed.

---

## Caddy

Caddy is the single local application gateway.

It binds to:

```text
127.0.0.1:8080
```

Typical routing:

```text
/api/*   -> FastAPI
/mcp*    -> FastAPI
/health  -> FastAPI
/*       -> Next.js
```

---

## Cloudflare Tunnel

Cloudflare Tunnel runs on the host rather than inside Docker.

It forwards the public hostname to:

```text
http://127.0.0.1:8080
```

This keeps tunnel credentials outside the application Compose stack.

---

## Docker networks

### backend

Internal-only network for application services.

Typical members:

- API
- worker
- connector scheduler
- PostgreSQL
- Redis
- MinIO
- Ollama

### edge

Used where gateway-facing connectivity is required.

### egress

Used by services that need outbound internet access.

Ollama uses this network for model pulls.

The GitHub worker also requires outbound access for GitHub API requests.

---

## Memory ingestion flow

```text
Source
  |
  v
Document / capture / connector object
  |
  v
Extraction
  |
  v
Chunking
  |
  v
Embedding
  |
  v
Local Qwen analysis
  |
  v
Candidate Memory Inbox
  |
  +--> new
  +--> duplicate
  +--> related
  +--> updates
  +--> conflicts
  |
  v
Human review
  |
  v
Permanent memory
```

Sources do not automatically become permanent memory.

---

## GitHub connector flow

```text
GitHub App
    |
installation token
    |
    v
GitHub API
    |
    v
connector scheduler
    |
    v
content hash comparison
    |
    +--> unchanged -> skip
    |
    v
source document
    |
    v
Memory Inbox
```

Supported v2.1 sources include:

- repository metadata
- README files
- documentation
- issues
- pull requests
- optional source code

---

## Browser Capture flow

```text
Chrome / Edge
     |
capture:write key
     |
     v
/api/v1/capture
     |
     v
source document
     |
     v
candidate analysis
     |
     v
Memory Inbox
```

The browser extension uses a dedicated write-only API scope.

---

## Knowledge Core

Engram v2 adds a richer knowledge layer.

### Entity Graph

Entities are extracted and linked to memories.

### Temporal memories

Memories may have:

```text
valid_from
valid_to
```

A newer fact can supersede an older one without deleting historical truth.

### Timeline

Date-aware events are extracted and displayed chronologically.

### Memory Health

Memory health checks include:

- duplicates
- conflicts
- stale facts
- low-confidence data
- weak provenance
- orphaned knowledge

---

## Security boundaries

Direct public access should never be provided to:

```text
PostgreSQL
Redis
MinIO
Ollama
FastAPI
Next.js
```

Only the Caddy gateway should be reachable by the host Cloudflare Tunnel.

---

## Future architecture

Planned major additions include:

- OAuth / OIDC for MCP clients
- more ingestion connectors
- disaster recovery automation
- hybrid retrieval
- namespaces / projects
- memory consolidation
- observability


## OAuth / MCP identity

Engram v2.2 acts as both the OAuth authorization server and the MCP protected resource server.

```text
MCP client
   |
   +--> Protected Resource Metadata
   |
   +--> OAuth Authorization Server Metadata
   |
   +--> user consent + PKCE authorization code
   |
   +--> short-lived mb_at_ access token
   |
   +--> /mcp
```

OAuth access tokens are bound to the canonical `/mcp` resource. Existing `mem_live_` API keys remain available for scripts and compatibility.


## Disaster Recovery Monitor

v2.3 adds a separate `dr-monitor` service.

It:

- inventories encrypted PostgreSQL and object backups
- hashes and verifies archive integrity
- runs isolated database restores
- validates pgvector
- checks source-object references
- records backup filesystem health
- optionally replicates encrypted artifacts off-host with rclone

The monitor does not receive Docker socket access and does not overwrite production during restore tests.
