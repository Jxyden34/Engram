import base64
import hashlib
import html
import http.client
import ipaddress
import json
import re
import secrets
import socket
import ssl
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.config import settings
from app.database import connect
from app.security import Principal, sha256


OAUTH_SCOPES = {
    "mcp:use",
    "memory:read",
    "memory:write",
    "memory:delete_request",
    "document:read",
}

BASIC_MCP_SCOPES = {
    "mcp:use",
    "memory:read",
    "document:read",
}

CLIENT_ID_RE = re.compile(r"^mb_client_[A-Za-z0-9_-]{20,}$")


def issuer() -> str:
    return settings().public_origin.rstrip("/")


def mcp_resource() -> str:
    return issuer() + "/mcp"


def protected_resource_metadata_url() -> str:
    return issuer() + "/.well-known/oauth-protected-resource/mcp"


def authorization_server_metadata() -> dict[str, Any]:
    root = issuer()
    payload: dict[str, Any] = {
        "issuer": root,
        "authorization_endpoint": root + "/oauth/authorize",
        "token_endpoint": root + "/oauth/token",
        "revocation_endpoint": root + "/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": sorted(OAUTH_SCOPES),
        "client_id_metadata_document_supported": True,
        "service_documentation": root + "/api/docs",
    }
    if settings().oauth_dcr_enabled:
        payload["registration_endpoint"] = root + "/oauth/register"
    return payload


def protected_resource_metadata() -> dict[str, Any]:
    return {
        "resource": mcp_resource(),
        "authorization_servers": [issuer()],
        "scopes_supported": sorted(OAUTH_SCOPES),
        "bearer_methods_supported": ["header"],
        "resource_documentation": issuer() + "/api/docs",
    }


def _normalize_resource(value: str | None) -> str:
    if not value:
        raise HTTPException(status_code=400, detail="resource is required")
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"https", "http"} or not parts.netloc or parts.fragment:
        raise HTTPException(status_code=400, detail="Invalid OAuth resource")
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        port = None
    netloc = host if port is None else f"{host}:{port}"
    path = parts.path.rstrip("/") or ""
    return urlunsplit((scheme, netloc, path, "", ""))


def validate_resource(value: str | None) -> str:
    normalized = _normalize_resource(value)
    expected = _normalize_resource(mcp_resource())
    if normalized != expected:
        raise HTTPException(status_code=400, detail="resource does not identify this MCP server")
    return mcp_resource()


def _validate_redirect_uri(uri: str) -> str:
    if not uri or len(uri) > 4000:
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")
    parts = urlsplit(uri)
    if parts.fragment or parts.username or parts.password:
        raise HTTPException(status_code=400, detail="redirect_uri must not contain credentials or fragments")

    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()

    if scheme == "https" and host:
        return uri

    if scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}:
        return uri

    raise HTTPException(
        status_code=400,
        detail="redirect_uri must use HTTPS or loopback/localhost HTTP",
    )


def _redirect_uri_matches(registered: str, requested: str) -> bool:
    if registered == requested:
        return True
    a = urlsplit(registered)
    b = urlsplit(requested)
    loopback = {"localhost", "127.0.0.1", "::1"}
    if (
        a.scheme.lower() == "http"
        and b.scheme.lower() == "http"
        and (a.hostname or "").lower() in loopback
        and (b.hostname or "").lower() == (a.hostname or "").lower()
        and a.path == b.path
        and a.query == b.query
        and not a.fragment
        and not b.fragment
    ):
        # Native loopback clients commonly bind an ephemeral local port.
        return True
    return False


def _validate_scope_string(scope: str | None, allowed: set[str] | None = None) -> list[str]:
    requested = [part for part in (scope or "").split() if part]
    if not requested:
        requested = sorted(BASIC_MCP_SCOPES)
    unknown = sorted(set(requested) - OAUTH_SCOPES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unsupported OAuth scope(s): {', '.join(unknown)}")
    if allowed is not None:
        denied = sorted(set(requested) - allowed)
        if denied:
            raise HTTPException(status_code=400, detail=f"Client is not allowed scope(s): {', '.join(denied)}")
    return sorted(set(requested))


def _client_id() -> str:
    return "mb_client_" + secrets.token_urlsafe(30)


def _authorization_code() -> str:
    return "mb_code_" + secrets.token_urlsafe(42)


def _access_token() -> str:
    return "mb_at_" + secrets.token_urlsafe(48)


def _refresh_token() -> str:
    return "mb_rt_" + secrets.token_urlsafe(56)


def _json_no_store(payload: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def oauth_error(error: str, description: str, status_code: int = 400) -> JSONResponse:
    return _json_no_store(
        {"error": error, "error_description": description},
        status_code=status_code,
    )


def _redirect_with_params(uri: str, params: dict[str, str | None]) -> RedirectResponse:
    parts = urlsplit(uri)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value is not None:
            query[key] = value
    target = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return RedirectResponse(target, status_code=302)


def _cleanup_expired():
    with connect() as conn:
        conn.execute(
            "DELETE FROM oauth_authorization_codes WHERE expires_at < now() - interval '1 day'"
        )
        conn.execute(
            """
            DELETE FROM oauth_access_tokens
            WHERE expires_at < now() - interval '7 days'
               OR (revoked_at IS NOT NULL AND revoked_at < now() - interval '7 days')
            """
        )
        conn.execute(
            """
            DELETE FROM oauth_refresh_tokens
            WHERE expires_at < now() - interval '30 days'
               OR (revoked_at IS NOT NULL AND revoked_at < now() - interval '30 days')
            """
        )
        conn.commit()


def create_static_client(
    name: str,
    redirect_uris: list[str],
    allowed_scopes: list[str],
    actor: str,
    owner_id: str | None,
):
    redirects = sorted({_validate_redirect_uri(value.strip()) for value in redirect_uris if value.strip()})
    if not redirects:
        raise HTTPException(status_code=400, detail="At least one redirect URI is required")
    scopes = _validate_scope_string(" ".join(allowed_scopes), OAUTH_SCOPES)

    client_id = _client_id()
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO oauth_clients(
                client_id, client_name, registration_type, redirect_uris,
                allowed_scopes, owner_id, created_by
            )
            VALUES (%s,%s,'static',%s,%s,%s,%s)
            RETURNING *
            """,
            (client_id, name, redirects, scopes, owner_id, actor),
        ).fetchone()
        conn.commit()
    return dict(row)


def update_static_client(client_id: str, changes: dict[str, Any]):
    with connect() as conn:
        current = conn.execute(
            "SELECT * FROM oauth_clients WHERE client_id=%s",
            (client_id,),
        ).fetchone()
    if not current:
        raise HTTPException(status_code=404, detail="OAuth client not found")

    if current["registration_type"] != "static":
        raise HTTPException(status_code=400, detail="Only pre-registered clients can be edited here")

    name = changes.get("client_name") or current["client_name"]
    redirects = current["redirect_uris"]
    if changes.get("redirect_uris") is not None:
        redirects = sorted({
            _validate_redirect_uri(value.strip())
            for value in changes["redirect_uris"]
            if value.strip()
        })
        if not redirects:
            raise HTTPException(status_code=400, detail="At least one redirect URI is required")

    scopes = current["allowed_scopes"]
    if changes.get("allowed_scopes") is not None:
        scopes = _validate_scope_string(" ".join(changes["allowed_scopes"]), OAUTH_SCOPES)

    active = current["is_active"] if changes.get("is_active") is None else bool(changes["is_active"])

    with connect() as conn:
        row = conn.execute(
            """
            UPDATE oauth_clients
            SET client_name=%s, redirect_uris=%s, allowed_scopes=%s,
                is_active=%s, updated_at=now()
            WHERE client_id=%s
            RETURNING *
            """,
            (name, redirects, scopes, active, client_id),
        ).fetchone()
        if not active:
            conn.execute(
                "UPDATE oauth_access_tokens SET revoked_at=coalesce(revoked_at,now()) WHERE client_id=%s",
                (client_id,),
            )
            conn.execute(
                "UPDATE oauth_refresh_tokens SET revoked_at=coalesce(revoked_at,now()) WHERE client_id=%s",
                (client_id,),
            )
            conn.execute(
                "UPDATE oauth_consents SET revoked_at=coalesce(revoked_at,now()) WHERE client_id=%s",
                (client_id,),
            )
        conn.commit()
    return dict(row)


def revoke_client(client_id: str):
    with connect() as conn:
        row = conn.execute(
            """
            UPDATE oauth_clients
            SET is_active=false, updated_at=now()
            WHERE client_id=%s
            RETURNING id, client_id, client_name
            """,
            (client_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="OAuth client not found")
        conn.execute(
            "UPDATE oauth_access_tokens SET revoked_at=coalesce(revoked_at,now()) WHERE client_id=%s",
            (client_id,),
        )
        conn.execute(
            "UPDATE oauth_refresh_tokens SET revoked_at=coalesce(revoked_at,now()) WHERE client_id=%s",
            (client_id,),
        )
        conn.execute(
            "UPDATE oauth_consents SET revoked_at=coalesce(revoked_at,now()) WHERE client_id=%s",
            (client_id,),
        )
        conn.commit()
    return dict(row)


def list_clients():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT c.*,
                   (SELECT count(*) FROM oauth_access_tokens t
                    WHERE t.client_id=c.client_id
                      AND t.revoked_at IS NULL AND t.expires_at > now()) AS active_access_tokens,
                   (SELECT count(*) FROM oauth_refresh_tokens r
                    WHERE r.client_id=c.client_id
                      AND r.revoked_at IS NULL AND r.expires_at > now()) AS active_refresh_tokens,
                   (SELECT max(coalesce(t.last_used_at,t.created_at))
                    FROM oauth_access_tokens t WHERE t.client_id=c.client_id) AS token_last_used_at
            FROM oauth_clients c
            ORDER BY c.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_consents():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT o.*, c.client_name, c.registration_type,
                   u.username,
                   (SELECT count(*) FROM oauth_access_tokens t
                    WHERE t.client_id=o.client_id AND t.user_id=o.user_id
                      AND t.revoked_at IS NULL AND t.expires_at > now()) AS active_access_tokens,
                   (SELECT count(*) FROM oauth_refresh_tokens r
                    WHERE r.client_id=o.client_id AND r.user_id=o.user_id
                      AND r.revoked_at IS NULL AND r.expires_at > now()) AS active_refresh_tokens
            FROM oauth_consents o
            JOIN oauth_clients c ON c.client_id=o.client_id
            JOIN users u ON u.id=o.user_id
            ORDER BY o.authorized_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def revoke_consent(consent_id: str):
    with connect() as conn:
        consent = conn.execute(
            "SELECT * FROM oauth_consents WHERE id=%s",
            (consent_id,),
        ).fetchone()
        if not consent:
            raise HTTPException(status_code=404, detail="OAuth consent not found")
        conn.execute(
            "UPDATE oauth_consents SET revoked_at=coalesce(revoked_at,now()) WHERE id=%s",
            (consent_id,),
        )
        conn.execute(
            """
            UPDATE oauth_access_tokens
            SET revoked_at=coalesce(revoked_at,now())
            WHERE client_id=%s AND user_id=%s AND resource=%s
            """,
            (consent["client_id"], consent["user_id"], consent["resource"]),
        )
        conn.execute(
            """
            UPDATE oauth_refresh_tokens
            SET revoked_at=coalesce(revoked_at,now())
            WHERE client_id=%s AND user_id=%s AND resource=%s
            """,
            (consent["client_id"], consent["user_id"], consent["resource"]),
        )
        conn.commit()
    return {"id": str(consent["id"]), "client_id": consent["client_id"]}


def oauth_summary():
    with connect() as conn:
        return {
            "issuer": issuer(),
            "resource": mcp_resource(),
            "oauth_metadata": issuer() + "/.well-known/oauth-authorization-server",
            "resource_metadata": protected_resource_metadata_url(),
            "authorization_endpoint": issuer() + "/oauth/authorize",
            "token_endpoint": issuer() + "/oauth/token",
            "cimd_supported": True,
            "dcr_enabled": settings().oauth_dcr_enabled,
            "access_token_minutes": settings().oauth_access_token_minutes,
            "refresh_token_days": settings().oauth_refresh_token_days,
            "active_clients": conn.execute(
                "SELECT count(*) AS n FROM oauth_clients WHERE is_active=true"
            ).fetchone()["n"],
            "active_consents": conn.execute(
                "SELECT count(*) AS n FROM oauth_consents WHERE revoked_at IS NULL"
            ).fetchone()["n"],
            "active_access_tokens": conn.execute(
                """
                SELECT count(*) AS n FROM oauth_access_tokens
                WHERE revoked_at IS NULL AND expires_at > now()
                """
            ).fetchone()["n"],
        }


def _resolve_public_host(hostname: str, port: int) -> list[str]:
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail="Client metadata hostname could not be resolved") from exc

    addresses = []
    for record in records:
        value = record[4][0]
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError:
            continue
        if not parsed.is_global:
            raise HTTPException(
                status_code=400,
                detail="Client metadata URL resolved to a non-public address",
            )
        addresses.append(value)

    if not addresses:
        raise HTTPException(status_code=400, detail="Client metadata hostname has no public address")
    return list(dict.fromkeys(addresses))


def _fetch_cimd(url: str) -> dict[str, Any]:
    parts = urlsplit(url)
    if parts.scheme.lower() != "https" or not parts.hostname or not parts.path or parts.path == "/":
        raise HTTPException(
            status_code=400,
            detail="CIMD client_id must be an HTTPS URL with a path component",
        )
    if parts.username or parts.password or parts.fragment:
        raise HTTPException(status_code=400, detail="Invalid CIMD client_id URL")

    port = parts.port or 443
    addresses = _resolve_public_host(parts.hostname, port)
    last_exc = None
    max_bytes = settings().oauth_cimd_max_kb * 1024

    for address in addresses:
        try:
            raw_sock = socket.create_connection(
                (address, port),
                timeout=settings().oauth_cimd_timeout_seconds,
            )
            context = ssl.create_default_context()
            tls = context.wrap_socket(raw_sock, server_hostname=parts.hostname)

            path = parts.path + (("?" + parts.query) if parts.query else "")
            host_header = parts.hostname if port == 443 else f"{parts.hostname}:{port}"
            request_bytes = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "Accept: application/json\r\n"
                "User-Agent: MemoryBank-OAuth/2.2\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            tls.sendall(request_bytes)

            response = http.client.HTTPResponse(tls)
            response.begin()
            if response.status != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"Client metadata URL returned HTTP {response.status}",
                )
            ctype = response.getheader("content-type", "")
            if "json" not in ctype.lower():
                raise HTTPException(status_code=400, detail="Client metadata is not JSON")

            raw = response.read(max_bytes + 1)
            tls.close()
            if len(raw) > max_bytes:
                raise HTTPException(status_code=400, detail="Client metadata document is too large")
            return json.loads(raw.decode("utf-8"))
        except HTTPException:
            raise
        except Exception as exc:
            last_exc = exc

    raise HTTPException(status_code=400, detail="Unable to securely fetch client metadata") from last_exc


def _load_client(client_id: str, redirect_uri: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM oauth_clients WHERE client_id=%s",
            (client_id,),
        ).fetchone()

    if row:
        if not row["is_active"]:
            raise HTTPException(status_code=400, detail="OAuth client is disabled")
        client = dict(row)
    elif client_id.startswith("https://"):
        metadata = _fetch_cimd(client_id)
        if metadata.get("client_id") != client_id:
            raise HTTPException(status_code=400, detail="CIMD client_id does not match document URL")

        name = str(metadata.get("client_name") or "").strip()
        redirects = metadata.get("redirect_uris") or []
        if not name or not isinstance(redirects, list):
            raise HTTPException(status_code=400, detail="CIMD requires client_name and redirect_uris")
        redirects = sorted({_validate_redirect_uri(str(value)) for value in redirects})

        if "authorization_code" not in (metadata.get("grant_types") or ["authorization_code"]):
            raise HTTPException(status_code=400, detail="CIMD client does not support authorization_code")
        if "code" not in (metadata.get("response_types") or ["code"]):
            raise HTTPException(status_code=400, detail="CIMD client does not support code response type")
        if metadata.get("token_endpoint_auth_method", "none") != "none":
            raise HTTPException(status_code=400, detail="MemoryBank v2.2 supports public OAuth clients only")

        with connect() as conn:
            row = conn.execute(
                """
                INSERT INTO oauth_clients(
                    client_id, client_name, registration_type, metadata_url,
                    redirect_uris, allowed_scopes, created_by, metadata
                )
                VALUES (%s,%s,'cimd',%s,%s,%s,'oauth:cimd',%s::jsonb)
                ON CONFLICT (client_id)
                DO UPDATE SET client_name=EXCLUDED.client_name,
                              redirect_uris=EXCLUDED.redirect_uris,
                              metadata=EXCLUDED.metadata,
                              updated_at=now()
                RETURNING *
                """,
                (
                    client_id,
                    name,
                    client_id,
                    redirects,
                    sorted(OAUTH_SCOPES),
                    json.dumps(metadata),
                ),
            ).fetchone()
            conn.commit()
        client = dict(row)
    else:
        raise HTTPException(status_code=400, detail="Unknown OAuth client")

    if redirect_uri is not None:
        _validate_redirect_uri(redirect_uri)
        if not any(_redirect_uri_matches(value, redirect_uri) for value in client["redirect_uris"]):
            raise HTTPException(status_code=400, detail="redirect_uri is not registered for this client")

    return client


def dynamic_register(metadata: dict[str, Any]):
    if not settings().oauth_dcr_enabled:
        raise HTTPException(status_code=404, detail="Dynamic client registration is disabled")

    redirects = metadata.get("redirect_uris")
    if not isinstance(redirects, list) or not redirects:
        raise HTTPException(status_code=400, detail="redirect_uris is required")
    redirects = sorted({_validate_redirect_uri(str(value)) for value in redirects})

    if "authorization_code" not in (metadata.get("grant_types") or ["authorization_code"]):
        raise HTTPException(status_code=400, detail="Only authorization_code is supported")
    if "code" not in (metadata.get("response_types") or ["code"]):
        raise HTTPException(status_code=400, detail="Only code response_type is supported")
    if metadata.get("token_endpoint_auth_method", "none") != "none":
        raise HTTPException(status_code=400, detail="Only public clients are supported")

    application_type = str(metadata.get("application_type") or "native")
    if application_type not in {"native", "web"}:
        raise HTTPException(status_code=400, detail="application_type must be native or web")

    client_id = _client_id()
    client_name = str(metadata.get("client_name") or "MCP Client")[:300]
    created_at = int(datetime.now(timezone.utc).timestamp())

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO oauth_clients(
                client_id, client_name, registration_type, redirect_uris,
                allowed_scopes, token_endpoint_auth_method, application_type,
                created_by, metadata
            )
            VALUES (%s,%s,'dynamic',%s,%s,'none',%s,'oauth:dcr',%s::jsonb)
            """,
            (
                client_id,
                client_name,
                redirects,
                sorted(OAUTH_SCOPES),
                application_type,
                json.dumps(metadata),
            ),
        )
        conn.commit()

    return {
        "client_id": client_id,
        "client_id_issued_at": created_at,
        "client_name": client_name,
        "redirect_uris": redirects,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": application_type,
    }


def validate_authorization_request(params: dict[str, str]) -> dict[str, Any]:
    if params.get("response_type") != "code":
        raise HTTPException(status_code=400, detail="response_type must be code")

    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    client = _load_client(client_id, redirect_uri)

    challenge = params.get("code_challenge", "")
    if not challenge or params.get("code_challenge_method") != "S256":
        raise HTTPException(status_code=400, detail="PKCE with code_challenge_method=S256 is required")
    if len(challenge) < 43 or len(challenge) > 128:
        raise HTTPException(status_code=400, detail="Invalid PKCE code_challenge")

    resource = validate_resource(params.get("resource"))
    scopes = _validate_scope_string(
        params.get("scope"),
        set(client["allowed_scopes"]),
    )

    return {
        "client": client,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "scopes": scopes,
        "state": params.get("state"),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": resource,
    }


def render_consent(request_data: dict[str, Any], username: str, csrf_token: str) -> HTMLResponse:
    client = request_data["client"]
    scopes = request_data["scopes"]
    scope_rows = "".join(
        f"<li><code>{html.escape(scope)}</code> — {html.escape(scope_description(scope))}</li>"
        for scope in scopes
    )

    hidden = {
        "response_type": "code",
        "client_id": request_data["client_id"],
        "redirect_uri": request_data["redirect_uri"],
        "scope": request_data["scope"],
        "state": request_data.get("state") or "",
        "code_challenge": request_data["code_challenge"],
        "code_challenge_method": request_data["code_challenge_method"],
        "resource": request_data["resource"],
        "csrf_token": csrf_token,
    }
    hidden_inputs = "".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(str(v), quote=True)}">'
        for k, v in hidden.items()
    )

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Authorize {html.escape(client['client_name'])} · MemoryBank</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#0b0d10; color:#f2f4f7; font:14px system-ui,-apple-system,sans-serif; }}
  main {{ width:min(620px,calc(100% - 32px)); background:#12161b; border:1px solid #2a313a; border-radius:18px; padding:28px; box-shadow:0 24px 80px #0008; }}
  .logo {{ width:42px;height:42px;border-radius:12px;display:grid;place-items:center;background:#b6ff4a;color:#10140b;font-weight:900;font-size:20px; }}
  h1 {{ margin:18px 0 7px; font-size:24px; }}
  p,li {{ color:#aeb6c2; line-height:1.55; }}
  code {{ color:#d9ff9f; }}
  .box {{ background:#0d1014;border:1px solid #242b33;border-radius:12px;padding:15px;margin:18px 0; }}
  .meta {{ color:#798390;font-size:12px;overflow-wrap:anywhere; }}
  .buttons {{ display:flex;gap:10px;margin-top:22px; }}
  button {{ flex:1;border:1px solid #343b44;border-radius:10px;padding:11px 14px;background:#171b21;color:#fff;font-weight:700;cursor:pointer; }}
  button.allow {{ background:#b6ff4a;border-color:#b6ff4a;color:#10140b; }}
</style>
</head>
<body>
<main>
  <div class="logo">M</div>
  <h1>Allow {html.escape(client['client_name'])}?</h1>
  <p>Signed in as <strong>{html.escape(username)}</strong>. This application is requesting access to your private MemoryBank.</p>
  <div class="box">
    <div class="meta">Client ID</div>
    <div>{html.escape(request_data['client_id'])}</div>
    <div class="meta" style="margin-top:12px">MCP resource</div>
    <div>{html.escape(request_data['resource'])}</div>
  </div>
  <strong>Requested permissions</strong>
  <ul>{scope_rows}</ul>
  <form method="post" action="/oauth/authorize">
    {hidden_inputs}
    <div class="buttons">
      <button name="decision" value="deny" type="submit">Deny</button>
      <button class="allow" name="decision" value="allow" type="submit">Allow access</button>
    </div>
  </form>
</main>
</body>
</html>"""
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


def scope_description(scope: str) -> str:
    return {
        "mcp:use": "Connect to the MemoryBank MCP server",
        "memory:read": "Search and read memories",
        "memory:write": "Create and update memories",
        "memory:delete_request": "Request deletion for human approval",
        "document:read": "Search text extracted from source documents",
    }.get(scope, scope)


def create_authorization_code(
    client_id: str,
    user_id: str,
    redirect_uri: str,
    scopes: list[str],
    resource: str,
    code_challenge: str,
) -> str:
    code = _authorization_code()
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings().oauth_authorization_code_minutes
    )

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO oauth_authorization_codes(
                code_hash, client_id, user_id, redirect_uri, scopes,
                resource, code_challenge, code_challenge_method, expires_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,'S256',%s)
            """,
            (
                sha256(code),
                client_id,
                user_id,
                redirect_uri,
                scopes,
                resource,
                code_challenge,
                expires,
            ),
        )
        conn.execute(
            """
            INSERT INTO oauth_consents(client_id,user_id,scopes,resource,authorized_at,revoked_at)
            VALUES (%s,%s,%s,%s,now(),NULL)
            ON CONFLICT (client_id,user_id,resource)
            DO UPDATE SET scopes=EXCLUDED.scopes,
                          authorized_at=now(),
                          revoked_at=NULL
            """,
            (client_id, user_id, scopes, resource),
        )
        conn.commit()
    return code


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _issue_token_pair(
    client_id: str,
    user_id: str,
    scopes: list[str],
    resource: str,
    family_id=None,
    parent_id=None,
):
    cfg = settings()
    access = _access_token()
    refresh = _refresh_token()
    now = datetime.now(timezone.utc)
    access_exp = now + timedelta(minutes=cfg.oauth_access_token_minutes)
    refresh_exp = now + timedelta(days=cfg.oauth_refresh_token_days)
    family_id = family_id or uuid4()

    with connect() as conn:
        refresh_row = conn.execute(
            """
            INSERT INTO oauth_refresh_tokens(
                token_hash, token_prefix, family_id, parent_id, client_id,
                user_id, scopes, resource, expires_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                sha256(refresh),
                refresh[:18],
                family_id,
                parent_id,
                client_id,
                user_id,
                scopes,
                resource,
                refresh_exp,
            ),
        ).fetchone()

        conn.execute(
            """
            INSERT INTO oauth_access_tokens(
                token_hash, token_prefix, client_id, user_id,
                refresh_token_id, scopes, resource, expires_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                sha256(access),
                access[:18],
                client_id,
                user_id,
                refresh_row["id"],
                scopes,
                resource,
                access_exp,
            ),
        )
        conn.execute(
            "UPDATE oauth_clients SET last_used_at=now() WHERE client_id=%s",
            (client_id,),
        )
        conn.execute(
            """
            UPDATE oauth_consents
            SET last_used_at=now()
            WHERE client_id=%s AND user_id=%s AND resource=%s
            """,
            (client_id, user_id, resource),
        )
        conn.commit()

    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": cfg.oauth_access_token_minutes * 60,
        "refresh_token": refresh,
        "scope": " ".join(scopes),
    }


def exchange_authorization_code(form: dict[str, str]):
    code = form.get("code", "")
    client_id = form.get("client_id", "")
    redirect_uri = form.get("redirect_uri", "")
    verifier = form.get("code_verifier", "")
    resource = validate_resource(form.get("resource"))

    if not code or not client_id or not redirect_uri or not verifier:
        return oauth_error("invalid_request", "code, client_id, redirect_uri, code_verifier and resource are required")

    _load_client(client_id, redirect_uri)

    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM oauth_authorization_codes
            WHERE code_hash=%s
            FOR UPDATE
            """,
            (sha256(code),),
        ).fetchone()

        if (
            not row
            or row["consumed_at"] is not None
            or row["expires_at"] <= datetime.now(timezone.utc)
        ):
            conn.rollback()
            return oauth_error("invalid_grant", "Authorization code is invalid, expired or already used")

        if row["client_id"] != client_id or row["redirect_uri"] != redirect_uri:
            conn.rollback()
            return oauth_error("invalid_grant", "Authorization code is not valid for this client")
        if _normalize_resource(row["resource"]) != _normalize_resource(resource):
            conn.rollback()
            return oauth_error("invalid_target", "resource does not match the authorization request")

        try:
            calculated = _pkce_s256(verifier)
        except Exception:
            conn.rollback()
            return oauth_error("invalid_grant", "Invalid PKCE code_verifier")

        if not secrets.compare_digest(calculated, row["code_challenge"]):
            conn.rollback()
            return oauth_error("invalid_grant", "PKCE verification failed")

        conn.execute(
            "UPDATE oauth_authorization_codes SET consumed_at=now() WHERE id=%s",
            (row["id"],),
        )
        conn.commit()

    _cleanup_expired()
    return _json_no_store(
        _issue_token_pair(
            row["client_id"],
            str(row["user_id"]),
            list(row["scopes"]),
            row["resource"],
        )
    )


def exchange_refresh_token(form: dict[str, str]):
    refresh = form.get("refresh_token", "")
    client_id = form.get("client_id", "")
    resource = validate_resource(form.get("resource"))

    if not refresh or not client_id:
        return oauth_error("invalid_request", "refresh_token, client_id and resource are required")

    _load_client(client_id)

    token_hash = sha256(refresh)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM oauth_refresh_tokens
            WHERE token_hash=%s
            FOR UPDATE
            """,
            (token_hash,),
        ).fetchone()

        if not row:
            conn.rollback()
            return oauth_error("invalid_grant", "Refresh token is invalid")

        if row["client_id"] != client_id or _normalize_resource(row["resource"]) != _normalize_resource(resource):
            conn.rollback()
            return oauth_error("invalid_grant", "Refresh token is not valid for this client or resource")

        now = datetime.now(timezone.utc)
        if row["revoked_at"] is not None or row["rotated_at"] is not None:
            # Rotation reuse detection. Revoke the entire family.
            conn.execute(
                """
                UPDATE oauth_refresh_tokens
                SET revoked_at=coalesce(revoked_at,now())
                WHERE family_id=%s
                """,
                (row["family_id"],),
            )
            conn.execute(
                """
                UPDATE oauth_access_tokens a
                SET revoked_at=coalesce(a.revoked_at,now())
                WHERE a.refresh_token_id IN (
                    SELECT id FROM oauth_refresh_tokens WHERE family_id=%s
                )
                """,
                (row["family_id"],),
            )
            conn.commit()
            return oauth_error("invalid_grant", "Refresh token reuse detected; token family revoked")

        if row["expires_at"] <= now:
            conn.rollback()
            return oauth_error("invalid_grant", "Refresh token has expired")

        requested_scopes = list(row["scopes"])
        if form.get("scope"):
            try:
                requested_scopes = _validate_scope_string(
                    form.get("scope"),
                    set(row["scopes"]),
                )
            except HTTPException as exc:
                conn.rollback()
                return oauth_error("invalid_scope", str(exc.detail))

        conn.execute(
            """
            UPDATE oauth_refresh_tokens
            SET rotated_at=now(), last_used_at=now()
            WHERE id=%s
            """,
            (row["id"],),
        )
        conn.commit()

    return _json_no_store(
        _issue_token_pair(
            client_id,
            str(row["user_id"]),
            requested_scopes,
            row["resource"],
            family_id=row["family_id"],
            parent_id=row["id"],
        )
    )


def revoke_token(form: dict[str, str]):
    token = form.get("token", "")
    client_id = form.get("client_id", "")
    if not token or not client_id:
        return oauth_error("invalid_request", "token and client_id are required")

    with connect() as conn:
        client = conn.execute(
            "SELECT client_id FROM oauth_clients WHERE client_id=%s AND is_active=true",
            (client_id,),
        ).fetchone()
        if not client:
            return oauth_error("invalid_client", "Unknown OAuth client", 401)

        token_hash = sha256(token)
        access = conn.execute(
            "SELECT id, client_id FROM oauth_access_tokens WHERE token_hash=%s",
            (token_hash,),
        ).fetchone()
        if access and access["client_id"] == client_id:
            conn.execute(
                "UPDATE oauth_access_tokens SET revoked_at=coalesce(revoked_at,now()) WHERE id=%s",
                (access["id"],),
            )

        refresh = conn.execute(
            "SELECT id, client_id, family_id FROM oauth_refresh_tokens WHERE token_hash=%s",
            (token_hash,),
        ).fetchone()
        if refresh and refresh["client_id"] == client_id:
            conn.execute(
                """
                UPDATE oauth_refresh_tokens
                SET revoked_at=coalesce(revoked_at,now())
                WHERE family_id=%s
                """,
                (refresh["family_id"],),
            )
            conn.execute(
                """
                UPDATE oauth_access_tokens a
                SET revoked_at=coalesce(a.revoked_at,now())
                WHERE a.refresh_token_id IN (
                    SELECT id FROM oauth_refresh_tokens WHERE family_id=%s
                )
                """,
                (refresh["family_id"],),
            )
        conn.commit()

    return _json_no_store({})


def oauth_access_token_principal(token: str, expected_resource: str | None = None) -> Principal | None:
    if not token.startswith("mb_at_"):
        return None

    with connect() as conn:
        row = conn.execute(
            """
            SELECT t.id, t.client_id, t.user_id, t.scopes, t.resource,
                   t.expires_at, c.client_name, c.is_active,
                   u.username, u.is_active AS user_active
            FROM oauth_access_tokens t
            JOIN oauth_clients c ON c.client_id=t.client_id
            JOIN users u ON u.id=t.user_id
            WHERE t.token_hash=%s AND t.revoked_at IS NULL
            """,
            (sha256(token),),
        ).fetchone()

        if (
            not row
            or not row["is_active"]
            or not row["user_active"]
            or row["expires_at"] <= datetime.now(timezone.utc)
        ):
            return None

        if expected_resource and _normalize_resource(row["resource"]) != _normalize_resource(expected_resource):
            return None

        conn.execute(
            "UPDATE oauth_access_tokens SET last_used_at=now() WHERE id=%s",
            (row["id"],),
        )
        conn.execute(
            "UPDATE oauth_clients SET last_used_at=now() WHERE client_id=%s",
            (row["client_id"],),
        )
        conn.execute(
            """
            UPDATE oauth_consents
            SET last_used_at=now()
            WHERE client_id=%s AND user_id=%s AND resource=%s
            """,
            (row["client_id"], row["user_id"], row["resource"]),
        )
        conn.commit()

    return Principal(
        actor=f"oauth:{row['client_name']}:{row['username']}",
        user_id=str(row["user_id"]),
        username=row["username"],
        is_admin=False,
        scopes=set(row["scopes"]),
        auth_type="oauth",
    )
