# OAuth and MCP Identity

MemoryBank v2.2 adds an OAuth authorization server for remote MCP clients.

The implementation is designed around the modern MCP authorization model:

- OAuth authorization code flow
- mandatory PKCE using `S256`
- short-lived opaque access tokens
- rotating refresh tokens
- refresh-token family reuse detection
- RFC 8707-style resource binding to the exact MemoryBank MCP endpoint
- OAuth Protected Resource Metadata
- OAuth Authorization Server Metadata
- Client ID Metadata Documents (CIMD)
- pre-registered clients
- legacy Dynamic Client Registration fallback
- user consent
- revocation
- per-client scopes
- audit events

Legacy `mem_live_...` API keys remain supported for scripts and older clients.

## Endpoints

```text
/.well-known/oauth-protected-resource
/.well-known/oauth-protected-resource/mcp
/.well-known/oauth-authorization-server

/oauth/authorize
/oauth/token
/oauth/revoke
/oauth/register

/mcp
```

## MCP resource

The canonical resource is:

```text
https://YOUR-HOST/mcp
```

OAuth authorization and token requests must include that `resource`.

Tokens issued for another resource are rejected.

## Default token lifetime

```text
Access token:  15 minutes
Refresh token: 30 days
Auth code:      5 minutes
```

Configure with:

```dotenv
OAUTH_ACCESS_TOKEN_MINUTES=15
OAUTH_REFRESH_TOKEN_DAYS=30
OAUTH_AUTHORIZATION_CODE_MINUTES=5
```

## Client registration

### Client ID Metadata Documents

Modern MCP clients can use an HTTPS URL as their `client_id`.

MemoryBank securely fetches the JSON metadata document, validates it, validates
the redirect URI, and caches the client registration.

Metadata retrieval:

- requires HTTPS
- requires a path component
- rejects non-public IP addresses
- connects to the already-resolved public IP to reduce DNS-rebinding risk
- validates TLS using the metadata hostname
- rejects redirects
- limits response size

### Pre-registration

Use **AI, API & OAuth** in the MemoryBank dashboard to create a client manually.

This returns a client ID beginning with:

```text
mb_client_
```

### Dynamic Client Registration

DCR remains available as a compatibility fallback for older MCP clients.

It can be disabled:

```dotenv
OAUTH_DCR_ENABLED=false
```

## PKCE

Authorization requests must use:

```text
code_challenge_method=S256
```

Plain PKCE is not supported.

## Refresh token rotation

Every refresh exchanges the old refresh token for a new one.

If a rotated refresh token is presented again, MemoryBank assumes token theft
and revokes the entire refresh-token family.

## Scope model

Supported OAuth scopes:

```text
mcp:use
memory:read
memory:write
memory:delete_request
document:read
```

The initial MCP challenge advertises a read-oriented baseline:

```text
mcp:use memory:read document:read
```

Clients can request additional scopes when needed.

## Existing API keys

Existing API keys continue to work.

OAuth is preferred for interactive MCP clients because:

- access tokens expire quickly
- refresh tokens rotate
- authorization is explicitly consented
- clients can be revoked independently
- access is resource-bound
- permissions are visible in the dashboard
