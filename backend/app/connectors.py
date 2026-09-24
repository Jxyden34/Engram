import base64
import binascii
import email.header
import hashlib
from html.parser import HTMLParser
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import jwt
from fastapi import HTTPException
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from redis import Redis
from rq import Queue

from app.config import settings
from app.database import DEFAULT_PROJECT_ID, connect, current_project_id, project_scope, project_job
from app.documents import store_bytes


GITHUB_API_VERSION = "2026-03-10"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_CALLBACK_PATH = "/api/v1/connectors/gmail/callback"

DOC_EXTENSIONS = {
    ".md", ".txt", ".rst", ".adoc", ".json", ".yaml", ".yml",
}
CODE_EXTENSIONS = {
    ".py", ".ps1", ".sh", ".bash", ".js", ".jsx", ".ts", ".tsx",
    ".go", ".rs", ".java", ".cs", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".sql", ".toml", ".ini", ".cfg", ".conf", ".xml", ".html", ".css",
}


def queue():
    return Queue("document-ingest", connection=Redis.from_url(settings().redis_url))


def capabilities():
    cfg = settings()
    key_path = Path(cfg.github_app_private_key_path)
    return {
        "github": {
            "available": bool(cfg.github_app_id and key_path.is_file()),
            "app_id_configured": bool(cfg.github_app_id),
            "private_key_present": key_path.is_file(),
            "private_key_path": cfg.github_app_private_key_path,
        },
        "browser_capture": {
            "available": True,
            "scope": "capture:write",
        },
        "gmail": {
            "available": bool(
                cfg.google_oauth_client_id
                and cfg.google_oauth_client_secret
                and _google_encryption_key()
            ),
            "scope": GMAIL_SCOPE,
            "redirect_uri": f"{cfg.public_origin.rstrip('/')}{GMAIL_CALLBACK_PATH}",
        },
    }


def _google_encryption_key() -> bytes | None:
    value = settings().google_token_encryption_key
    if not value:
        return None
    try:
        key = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None
    return key if len(key) == 32 else None


def _encrypt_google_token(token: str, connector_id: str) -> str:
    key = _google_encryption_key()
    if not key:
        raise RuntimeError("GOOGLE_TOKEN_ENCRYPTION_KEY must be a base64-encoded 32-byte key")
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce, token.encode("utf-8"), connector_id.encode())
    return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def _decrypt_google_token(ciphertext: str, connector_id: str) -> str:
    key = _google_encryption_key()
    if not key:
        raise RuntimeError("GOOGLE_TOKEN_ENCRYPTION_KEY must be a base64-encoded 32-byte key")
    try:
        value = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        token = AESGCM(key).decrypt(value[:12], value[12:], connector_id.encode())
        return token.decode("utf-8")
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("Gmail credential could not be decrypted") from exc


def _gmail_config(config: dict[str, Any]) -> dict[str, Any]:
    query = str(config.get("query") or "newer_than:30d").strip()
    if len(query) > 1000:
        raise HTTPException(status_code=400, detail="Gmail search query is too long")
    label_ids = config.get("label_ids", ["INBOX"])
    if not isinstance(label_ids, list) or len(label_ids) > 20:
        raise HTTPException(status_code=400, detail="Gmail labels must be a list of at most 20 IDs")
    labels = sorted({str(label).strip().upper() for label in label_ids})
    if any(not re.fullmatch(r"[A-Z0-9_-]{1,100}", label) for label in labels):
        raise HTTPException(status_code=400, detail="Gmail label IDs contain invalid characters")
    try:
        limit = min(max(int(config.get("max_messages_per_sync", 100)), 1), 500)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Gmail sync limit must be a number") from exc
    return {"query": query or "newer_than:30d", "label_ids": labels, "max_messages_per_sync": limit}


def start_gmail_oauth(data: dict[str, Any], actor: str, owner_id: str, session_hash: str) -> str:
    cfg = settings()
    if not cfg.google_oauth_client_id or not cfg.google_oauth_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth client is not configured")
    if not _google_encryption_key():
        raise HTTPException(status_code=503, detail="Gmail token encryption key is not configured")
    state = secrets.token_urlsafe(32)
    state_data = json.dumps({
        "actor": actor,
        "owner_id": owner_id,
        "session_hash": session_hash,
        "project_id": current_project_id(),
        "name": str(data.get("name") or "Gmail").strip()[:200] or "Gmail",
        "config": _gmail_config(data),
    })
    redis = Redis.from_url(cfg.redis_url)
    if not redis.set(f"gmail:oauth:{hashlib.sha256(state.encode()).hexdigest()}", state_data, ex=600, nx=True):
        raise HTTPException(status_code=503, detail="Could not start Gmail authorization")
    redirect_uri = f"{cfg.public_origin.rstrip('/')}{GMAIL_CALLBACK_PATH}"
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": cfg.google_oauth_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })


def finish_gmail_oauth(state: str, code: str, session_hash: str) -> tuple[str, str]:
    cfg = settings()
    if not cfg.google_oauth_client_id or not cfg.google_oauth_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth client is not configured")
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    value = Redis.from_url(cfg.redis_url).getdel(f"gmail:oauth:{state_hash}")
    if not value:
        raise HTTPException(status_code=400, detail="Gmail authorization state expired or was already used")
    data = json.loads(value)
    if not secrets.compare_digest(data["session_hash"], session_hash):
        raise HTTPException(status_code=403, detail="Gmail authorization must finish in the same browser session")
    if data.get("project_id", DEFAULT_PROJECT_ID) != current_project_id():
        raise HTTPException(status_code=409, detail="Select the original project before finishing Gmail authorization")
    if not code:
        raise HTTPException(status_code=400, detail="Google authorization was cancelled")
    redirect_uri = f"{cfg.public_origin.rstrip('/')}{GMAIL_CALLBACK_PATH}"
    try:
        response = httpx.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": cfg.google_oauth_client_id,
            "client_secret": cfg.google_oauth_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=30)
        if response.is_error:
            raise HTTPException(status_code=502, detail="Google token exchange failed")
        tokens = response.json()
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise HTTPException(status_code=502, detail="Google did not return offline access; retry authorization")
        profile = httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile",
                            headers={"Authorization": f"Bearer {tokens['access_token']}"}, timeout=30)
        if profile.is_error:
            raise HTTPException(status_code=502, detail="Could not read the authorized Gmail profile")
        email_address = str(profile.json().get("emailAddress") or "").strip().lower()
        if not email_address:
            raise HTTPException(status_code=502, detail="Google returned no Gmail address")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not complete Google authorization") from exc

    connector_id = str(uuid4())
    credential = _encrypt_google_token(refresh_token, connector_id)
    name = data["name"] if data["name"] != "Gmail" else f"Gmail · {email_address}"
    with connect() as conn:
        row = conn.execute("""
            INSERT INTO connectors(id,owner_id,connector_type,name,schedule_minutes,config,
                                   credential_ciphertext,created_by)
            VALUES (%s,%s,'gmail',%s,360,%s::jsonb,%s,%s)
            RETURNING id
        """, (connector_id, data["owner_id"], name,
              json.dumps({**data["config"], "email_address": email_address}),
              credential, data["actor"])).fetchone()
        conn.commit()
    return str(row["id"]), email_address


def cancel_gmail_oauth(state: str, session_hash: str) -> None:
    value = Redis.from_url(settings().redis_url).getdel(
        f"gmail:oauth:{hashlib.sha256(state.encode()).hexdigest()}"
    )
    if value:
        data = json.loads(value)
        if not secrets.compare_digest(data["session_hash"], session_hash):
            raise HTTPException(status_code=403, detail="Gmail authorization session did not match")


def revoke_gmail_token(connector_id: str, ciphertext: str | None) -> None:
    if ciphertext:
        try:
            token = _decrypt_google_token(ciphertext, connector_id)
            httpx.post("https://oauth2.googleapis.com/revoke", data={"token": token}, timeout=10)
        except (RuntimeError, httpx.HTTPError):
            pass


def _validate_github_config(config: dict[str, Any]) -> dict[str, Any]:
    installation_id = str(config.get("installation_id") or "").strip()
    if not installation_id.isdigit():
        raise HTTPException(status_code=400, detail="GitHub installation_id must be numeric")

    repositories = config.get("repositories") or []
    if isinstance(repositories, str):
        repositories = [
            value.strip() for value in repositories.split(",") if value.strip()
        ]
    if not isinstance(repositories, list):
        raise HTTPException(status_code=400, detail="repositories must be a list")

    clean_repositories = []
    for repo in repositories:
        repo = str(repo).strip()
        if repo.count("/") != 1:
            raise HTTPException(
                status_code=400,
                detail=f"Repository must use owner/name format: {repo}",
            )
        clean_repositories.append(repo.lower())

    return {
        "installation_id": installation_id,
        "repositories": clean_repositories,
        "sync_readme": bool(config.get("sync_readme", True)),
        "sync_docs": bool(config.get("sync_docs", True)),
        "sync_issues": bool(config.get("sync_issues", True)),
        "sync_pulls": bool(config.get("sync_pulls", True)),
        "sync_code": bool(config.get("sync_code", False)),
        "max_items_per_sync": min(
            max(int(config.get("max_items_per_sync", settings().github_max_items_per_sync)), 10),
            2000,
        ),
        "max_file_kb": min(
            max(int(config.get("max_file_kb", settings().github_max_file_kb)), 16),
            4096,
        ),
    }


def _public_connector(row: Any) -> dict[str, Any]:
    result = dict(row)
    result.pop("credential_ciphertext", None)
    return result


def create_connector(data: dict[str, Any], actor: str, owner_id: str | None):
    connector_type = str(data.get("connector_type") or "").strip().lower()
    if connector_type != "github":
        raise HTTPException(status_code=400, detail="Use Gmail authorization to create Gmail connectors")

    config = _validate_github_config(data.get("config") or {})
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO connectors(
                owner_id, connector_type, name, schedule_minutes, config, created_by
            )
            VALUES (%s,%s,%s,%s,%s::jsonb,%s)
            RETURNING *
            """,
            (
                owner_id,
                connector_type,
                data["name"],
                data.get("schedule_minutes", 30),
                json.dumps(config),
                actor,
            ),
        ).fetchone()
        conn.commit()
    return _public_connector(row)


def update_connector(connector_id: str, changes: dict[str, Any]):
    with connect() as conn:
        current = conn.execute(
            "SELECT * FROM connectors WHERE id=%s",
            (connector_id,),
        ).fetchone()
    if not current:
        raise HTTPException(status_code=404, detail="Connector not found")

    config = current["config"]
    if changes.get("config") is not None:
        if current["connector_type"] == "github":
            config = _validate_github_config(changes["config"])
        else:
            config = {
                **_gmail_config(changes["config"]),
                "email_address": current["config"].get("email_address", ""),
            }

    name = changes.get("name") or current["name"]
    enabled = current["enabled"] if changes.get("enabled") is None else changes["enabled"]
    schedule = changes.get("schedule_minutes") or current["schedule_minutes"]

    with connect() as conn:
        row = conn.execute(
            """
            UPDATE connectors
            SET name=%s, enabled=%s, schedule_minutes=%s, config=%s::jsonb,
                next_sync_at=CASE WHEN %s THEN LEAST(next_sync_at, now()) ELSE next_sync_at END,
                updated_at=now()
            WHERE id=%s
            RETURNING *
            """,
            (
                name,
                enabled,
                schedule,
                json.dumps(config),
                enabled,
                connector_id,
            ),
        ).fetchone()
        conn.commit()
    return _public_connector(row)


def delete_connector(connector_id: str):
    with connect() as conn:
        current = conn.execute(
            "SELECT id, connector_type, credential_ciphertext FROM connectors WHERE id=%s",
            (connector_id,),
        ).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Connector not found")
        row = conn.execute(
            "DELETE FROM connectors WHERE id=%s RETURNING id, name",
            (connector_id,),
        ).fetchone()
        conn.commit()
    if current["connector_type"] == "gmail":
        revoke_gmail_token(connector_id, current["credential_ciphertext"])
    return dict(row)


def list_connectors():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT c.*,
                   (
                     SELECT count(*)
                     FROM connector_items i
                     WHERE i.connector_id=c.id
                   ) AS item_count
            FROM connectors c
            ORDER BY c.created_at DESC
            """
        ).fetchall()
    return [_public_connector(row) for row in rows]


def list_runs(connector_id: str | None = None, limit: int = 100):
    clauses = []
    params: list[Any] = []
    if connector_id:
        clauses.append("r.connector_id=%s")
        params.append(connector_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*, c.name AS connector_name, c.connector_type
            FROM connector_sync_runs r
            JOIN connectors c ON c.id=r.connector_id
            {where}
            ORDER BY r.created_at DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def queue_sync(connector_id: str):
    with connect() as conn:
        connector = conn.execute(
            "SELECT id, enabled FROM connectors WHERE id=%s",
            (connector_id,),
        ).fetchone()
        if not connector:
            raise HTTPException(status_code=404, detail="Connector not found")

        run = conn.execute(
            """
            INSERT INTO connector_sync_runs(connector_id)
            VALUES (%s)
            RETURNING *
            """,
            (connector_id,),
        ).fetchone()
        conn.execute(
            """
            UPDATE connectors
            SET next_sync_at=now() + (schedule_minutes || ' minutes')::interval,
                updated_at=now()
            WHERE id=%s
            """,
            (connector_id,),
        )
        conn.commit()

    queue().enqueue(
        "app.connectors.sync_connector",
        connector_id,
        str(run["id"]),
        job_timeout="2h",
        meta={"project_id": current_project_id()},
    )
    return dict(run)


def queue_due_connectors():
    with connect() as conn:
        project_ids = [str(row["id"]) for row in conn.execute("SELECT id FROM projects").fetchall()]
    return sum(_queue_due_connectors_in_project(project_id) for project_id in project_ids)


def _queue_due_connectors_in_project(project_id: str):
    with project_scope(project_id):
        return _queue_due_connectors_scoped()


def _queue_due_connectors_scoped():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM connectors
            WHERE enabled=true AND next_sync_at <= now()
            ORDER BY next_sync_at
            LIMIT 50
            FOR UPDATE SKIP LOCKED
            """
        ).fetchall()
        connector_ids = [str(row["id"]) for row in rows]

        for connector_id in connector_ids:
            conn.execute(
                """
                UPDATE connectors
                SET next_sync_at=now() + (schedule_minutes || ' minutes')::interval,
                    updated_at=now()
                WHERE id=%s
                """,
                (connector_id,),
            )
        conn.commit()

    queued = 0
    for connector_id in connector_ids:
        with connect() as conn:
            run = conn.execute(
                "INSERT INTO connector_sync_runs(connector_id) VALUES (%s) RETURNING id",
                (connector_id,),
            ).fetchone()
            conn.commit()
        queue().enqueue(
            "app.connectors.sync_connector",
            connector_id,
            str(run["id"]),
            job_timeout="2h",
            meta={"project_id": current_project_id()},
        )
        queued += 1
    return queued


def _github_jwt() -> str:
    cfg = settings()
    if not cfg.github_app_id:
        raise RuntimeError("GITHUB_APP_ID is not configured")

    key_path = Path(cfg.github_app_private_key_path)
    if not key_path.is_file():
        raise RuntimeError(
            f"GitHub App private key not found at {cfg.github_app_private_key_path}"
        )

    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iat": int((now - timedelta(seconds=60)).timestamp()),
            "exp": int((now + timedelta(minutes=9)).timestamp()),
            "iss": str(cfg.github_app_id),
        },
        key_path.read_text(encoding="utf-8"),
        algorithm="RS256",
    )


def _installation_token(installation_id: str) -> str:
    app_jwt = _github_jwt()
    response = httpx.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {app_jwt}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["token"]


def _github_client(token: str):
    return httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        timeout=60,
        follow_redirects=True,
    )


def _paginate(client: httpx.Client, path: str, params: dict | None = None, limit=1000):
    output = []
    page = 1
    while len(output) < limit:
        query = dict(params or {})
        query.update({"per_page": 100, "page": page})
        response = client.get(path, params=query)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "repositories" in payload:
            batch = payload["repositories"]
        elif isinstance(payload, list):
            batch = payload
        else:
            batch = []
        output.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return output[:limit]


class _PlainTextHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        elif tag in {"br", "p", "div", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"} and self.hidden:
            self.hidden -= 1
        elif tag in {"p", "div", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _gmail_body(part: dict[str, Any]) -> str:
    mime_type = part.get("mimeType")
    data = (part.get("body") or {}).get("data")
    if mime_type == "text/plain" and data:
        try:
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
        except (ValueError, binascii.Error):
            return ""
    if mime_type == "text/html" and data:
        try:
            html = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            parser = _PlainTextHTML()
            parser.feed(html)
            return "".join(parser.parts)
        except (ValueError, binascii.Error):
            return ""
    children = part.get("parts") or []
    for child in children:
        text = _gmail_body(child)
        if text:
            return text
    return ""


def _decode_header(value: str) -> str:
    try:
        return str(email.header.make_header(email.header.decode_header(value)))
    except (LookupError, UnicodeError, ValueError):
        return value


def _gmail_access_token(connector: dict[str, Any]) -> str:
    refresh_token = _decrypt_google_token(
        connector["credential_ciphertext"], str(connector["id"])
    )
    cfg = settings()
    response = httpx.post("https://oauth2.googleapis.com/token", data={
        "client_id": cfg.google_oauth_client_id,
        "client_secret": cfg.google_oauth_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=30)
    if response.is_error:
        raise RuntimeError(f"Google access token refresh failed (HTTP {response.status_code})")
    token_data = response.json()
    if token_data.get("refresh_token"):
        encrypted = _encrypt_google_token(token_data["refresh_token"], str(connector["id"]))
        with connect() as conn:
            conn.execute("UPDATE connectors SET credential_ciphertext=%s WHERE id=%s",
                         (encrypted, connector["id"]))
            conn.commit()
    return token_data["access_token"]


def _sync_gmail(connector: dict, run_id: str, counters: dict[str, int]) -> None:
    config = _gmail_config(connector["config"])
    token = _gmail_access_token(connector)
    email_address = str(connector["config"]["email_address"])
    params: dict[str, Any] = {"maxResults": min(config["max_messages_per_sync"], 100)}
    if config["query"]:
        params["q"] = config["query"]
    if config["label_ids"]:
        params["labelIds"] = config["label_ids"]

    with httpx.Client(
        base_url="https://gmail.googleapis.com/gmail/v1/users/me/",
        headers={"Authorization": f"Bearer {token}"}, timeout=45,
    ) as client:
        page_token = None
        while counters["seen"] < config["max_messages_per_sync"]:
            if page_token:
                params["pageToken"] = page_token
            listing = client.get("messages", params=params)
            listing.raise_for_status()
            result = listing.json()
            messages = result.get("messages") or []
            if not messages:
                break
            for item in messages:
                if counters["seen"] >= config["max_messages_per_sync"]:
                    break
                message_id = str(item.get("id") or "")
                if not message_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", message_id):
                    counters["errors"] += 1
                    continue
                message_response = client.get(f"messages/{message_id}", params={
                    "format": "full",
                    "fields": "id,threadId,internalDate,labelIds,snippet,payload",
                })
                if message_response.status_code == 404:
                    counters["skipped"] += 1
                    continue
                message_response.raise_for_status()
                message = message_response.json()
                headers = {
                    str(h.get("name", "")).lower(): str(h.get("value", ""))
                    for h in (message.get("payload") or {}).get("headers", [])
                }
                subject = " ".join(_decode_header(headers.get("subject", "(no subject)")).splitlines())
                sender = " ".join(_decode_header(headers.get("from", "Unknown sender")).splitlines())
                date_value = headers.get("date", "")
                body = _gmail_body(message.get("payload") or {})
                if not body:
                    body = str(message.get("snippet") or "")
                body = body[:262144]
                label_ids = message.get("labelIds") or []
                internal_date = message.get("internalDate")
                updated = None
                if internal_date:
                    updated = datetime.fromtimestamp(int(internal_date) / 1000, timezone.utc).isoformat()
                url = f"https://mail.google.com/mail/u/0/#all/{message_id}"
                content = (
                    f"# {subject}\n\n- From: {sender}\n- Date: {date_value}\n"
                    f"- Gmail label IDs: {', '.join(label_ids)}\n\n## Message\n\n{body}\n"
                ).encode("utf-8")
                counters["seen"] += 1
                changed = _upsert_source_item(
                    connector, run_id, f"gmail:{email_address}:{message_id}",
                    "email", subject, url, content,
                    f"gmail/{email_address}/{message_id}.md", "text/markdown",
                    updated, {"mailbox": email_address, "thread_id": message.get("threadId"),
                              "label_ids": label_ids}, source_type="gmail",
                )
                counters["changed"] += int(bool(changed))
                counters["skipped"] += int(not changed)
            page_token = result.get("nextPageToken")
            if not page_token:
                break


def _markdown_repo(repo: dict) -> bytes:
    topics = ", ".join(repo.get("topics") or []) or "None"
    text = f"""# Repository: {repo["full_name"]}

- URL: {repo["html_url"]}
- Visibility: {repo.get("visibility")}
- Default branch: {repo.get("default_branch")}
- Language: {repo.get("language")}
- Topics: {topics}
- Stars: {repo.get("stargazers_count", 0)}
- Forks: {repo.get("forks_count", 0)}
- Archived: {repo.get("archived", False)}

## Description

{repo.get("description") or "No description."}
"""
    return text.encode("utf-8")


def _markdown_issue(repo_name: str, item: dict, kind: str) -> bytes:
    labels = ", ".join(
        value.get("name", "") for value in item.get("labels", []) if value.get("name")
    ) or "None"
    users = ", ".join(
        value.get("login", "") for value in item.get("assignees", []) if value.get("login")
    ) or "None"

    text = f"""# {kind.title()} #{item["number"]}: {item.get("title") or "Untitled"}

- Repository: {repo_name}
- State: {item.get("state")}
- URL: {item.get("html_url")}
- Author: {(item.get("user") or {}).get("login")}
- Labels: {labels}
- Assignees: {users}
- Created: {item.get("created_at")}
- Updated: {item.get("updated_at")}
- Closed: {item.get("closed_at")}

## Body

{item.get("body") or "No body."}
"""
    return text.encode("utf-8")


def _upsert_source_item(
    connector: dict,
    run_id: str,
    external_id: str,
    item_type: str,
    title: str,
    external_url: str | None,
    raw: bytes,
    filename: str,
    content_type: str,
    external_updated_at: str | None,
    metadata: dict[str, Any],
    source_type: str = "github",
):
    digest = hashlib.sha256(raw).hexdigest()

    with connect() as conn:
        existing = conn.execute(
            """
            SELECT id, content_hash, document_id
            FROM connector_items
            WHERE connector_id=%s AND external_id=%s
            """,
            (connector["id"], external_id),
        ).fetchone()

        if existing and existing["content_hash"] == digest:
            conn.execute(
                """
                UPDATE connector_items
                SET last_seen_at=now(), external_url=%s, title=%s,
                    external_updated_at=%s, metadata=%s::jsonb
                WHERE id=%s
                """,
                (
                    external_url,
                    title,
                    external_updated_at,
                    json.dumps(metadata),
                    existing["id"],
                ),
            )
            conn.commit()
            return False

    document = store_bytes(
        raw,
        filename,
        content_type,
        f"connector:{connector['name']}",
        str(connector["owner_id"]) if connector["owner_id"] else None,
        source_type=source_type,
        source_ref=external_url,
        source_metadata={
            "connector_id": str(connector["id"]),
            "connector_name": connector["name"],
            "source_type": source_type,
            "external_id": external_id,
            "item_type": item_type,
            **metadata,
        },
        dedupe=False,
    )

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO connector_items(
                connector_id, external_id, item_type, external_url, title,
                content_hash, external_updated_at, document_id, metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (connector_id, external_id)
            DO UPDATE SET
                item_type=EXCLUDED.item_type,
                external_url=EXCLUDED.external_url,
                title=EXCLUDED.title,
                content_hash=EXCLUDED.content_hash,
                external_updated_at=EXCLUDED.external_updated_at,
                document_id=EXCLUDED.document_id,
                metadata=EXCLUDED.metadata,
                last_seen_at=now()
            """,
            (
                connector["id"],
                external_id,
                item_type,
                external_url,
                title,
                digest,
                external_updated_at,
                document["id"],
                json.dumps(metadata),
            ),
        )
        conn.commit()
    return True


def _sync_repo(client, connector, run_id, repo, config, counters):
    repo_name = repo["full_name"]
    prefix = f"github/{repo_name}"

    def ingest(*args, **kwargs):
        counters["seen"] += 1
        if counters["seen"] > config["max_items_per_sync"]:
            counters["skipped"] += 1
            return False
        changed = _upsert_source_item(connector, run_id, *args, **kwargs)
        if changed:
            counters["changed"] += 1
        else:
            counters["skipped"] += 1
        return changed

    ingest(
        f"repo:{repo_name}",
        "repository",
        repo_name,
        repo.get("html_url"),
        _markdown_repo(repo),
        f"{prefix}/repository.md",
        "text/markdown",
        repo.get("updated_at"),
        {"repository": repo_name},
    )

    if config["sync_readme"]:
        response = client.get(f"/repos/{repo_name}/readme")
        if response.status_code == 200:
            data = response.json()
            try:
                raw = base64.b64decode(data.get("content") or "")
                ingest(
                    f"readme:{repo_name}",
                    "readme",
                    f"{repo_name} README",
                    data.get("html_url") or repo.get("html_url"),
                    raw,
                    f"{prefix}/{data.get('path') or 'README.md'}",
                    "text/markdown",
                    repo.get("pushed_at"),
                    {"repository": repo_name, "path": data.get("path")},
                )
            except Exception:
                counters["errors"] += 1

    if config["sync_issues"] and counters["seen"] < config["max_items_per_sync"]:
        issues = _paginate(
            client,
            f"/repos/{repo_name}/issues",
            {"state": "all", "sort": "updated", "direction": "desc"},
            limit=min(200, config["max_items_per_sync"]),
        )
        for issue in issues:
            if issue.get("pull_request"):
                continue
            if counters["seen"] >= config["max_items_per_sync"]:
                break
            ingest(
                f"issue:{repo_name}:{issue['number']}",
                "issue",
                f"{repo_name} issue #{issue['number']}: {issue.get('title')}",
                issue.get("html_url"),
                _markdown_issue(repo_name, issue, "issue"),
                f"{prefix}/issues/{issue['number']}.md",
                "text/markdown",
                issue.get("updated_at"),
                {"repository": repo_name, "number": issue["number"]},
            )

    if config["sync_pulls"] and counters["seen"] < config["max_items_per_sync"]:
        pulls = _paginate(
            client,
            f"/repos/{repo_name}/pulls",
            {"state": "all", "sort": "updated", "direction": "desc"},
            limit=min(200, config["max_items_per_sync"]),
        )
        for pull in pulls:
            if counters["seen"] >= config["max_items_per_sync"]:
                break
            ingest(
                f"pull:{repo_name}:{pull['number']}",
                "pull_request",
                f"{repo_name} PR #{pull['number']}: {pull.get('title')}",
                pull.get("html_url"),
                _markdown_issue(repo_name, pull, "pull request"),
                f"{prefix}/pulls/{pull['number']}.md",
                "text/markdown",
                pull.get("updated_at"),
                {"repository": repo_name, "number": pull["number"]},
            )

    if (config["sync_docs"] or config["sync_code"]) and counters["seen"] < config["max_items_per_sync"]:
        branch = repo.get("default_branch") or "main"
        response = client.get(
            f"/repos/{repo_name}/git/trees/{branch}",
            params={"recursive": "1"},
        )
        if response.status_code == 200:
            tree_payload = response.json()
            for entry in tree_payload.get("tree", []):
                if counters["seen"] >= config["max_items_per_sync"]:
                    break
                if entry.get("type") != "blob":
                    continue

                path = entry.get("path") or ""
                suffix = Path(path).suffix.lower()
                lower = path.lower()
                is_doc = (
                    suffix in DOC_EXTENSIONS
                    and (
                        lower.startswith("docs/")
                        or "/docs/" in lower
                        or lower.startswith(".github/")
                        or "readme" in Path(lower).name
                        or Path(lower).name in {"contributing.md", "changelog.md", "security.md"}
                    )
                )
                is_code = suffix in CODE_EXTENSIONS

                if not ((config["sync_docs"] and is_doc) or (config["sync_code"] and is_code)):
                    continue

                size = int(entry.get("size") or 0)
                if size > config["max_file_kb"] * 1024:
                    counters["skipped"] += 1
                    continue

                blob = client.get(f"/repos/{repo_name}/git/blobs/{entry['sha']}")
                if blob.status_code != 200:
                    counters["errors"] += 1
                    continue
                payload = blob.json()
                if payload.get("encoding") != "base64":
                    counters["skipped"] += 1
                    continue

                try:
                    raw = base64.b64decode(payload.get("content") or "")
                except Exception:
                    counters["errors"] += 1
                    continue

                ingest(
                    f"file:{repo_name}:{path}",
                    "repository_file",
                    f"{repo_name}: {path}",
                    f"{repo.get('html_url')}/blob/{branch}/{path}",
                    raw,
                    f"{prefix}/files/{path}",
                    "text/plain",
                    repo.get("pushed_at"),
                    {
                        "repository": repo_name,
                        "path": path,
                        "sha": entry.get("sha"),
                        "branch": branch,
                    },
                )


@project_job
def sync_connector(connector_id: str, run_id: str):
    with connect() as conn:
        connector = conn.execute(
            "SELECT * FROM connectors WHERE id=%s",
            (connector_id,),
        ).fetchone()
        if not connector:
            return
        conn.execute(
            """
            UPDATE connector_sync_runs
            SET status='processing', started_at=now()
            WHERE id=%s
            """,
            (run_id,),
        )
        conn.commit()

    counters = {"seen": 0, "changed": 0, "skipped": 0, "errors": 0}

    try:
        if connector["connector_type"] == "github":
            config = _validate_github_config(connector["config"])
            token = _installation_token(config["installation_id"])
            with _github_client(token) as client:
                repositories = _paginate(client, "/installation/repositories", limit=1000)
                wanted = set(config["repositories"])
                if wanted:
                    repositories = [repo for repo in repositories
                                    if repo["full_name"].lower() in wanted]
                for repo in repositories:
                    if counters["seen"] >= config["max_items_per_sync"]:
                        break
                    try:
                        _sync_repo(client, dict(connector), run_id, repo, config, counters)
                    except Exception:
                        counters["errors"] += 1
        elif connector["connector_type"] == "gmail":
            if not connector["credential_ciphertext"]:
                raise RuntimeError("Gmail authorization is missing; reconnect the account")
            _sync_gmail(dict(connector), run_id, counters)
        else:
            raise RuntimeError(f"Unsupported connector type: {connector['connector_type']}")

        with connect() as conn:
            conn.execute(
                """
                UPDATE connector_sync_runs
                SET status='ready', items_seen=%s, items_changed=%s,
                    items_skipped=%s, error_count=%s, completed_at=now()
                WHERE id=%s
                """,
                (
                    counters["seen"],
                    counters["changed"],
                    counters["skipped"],
                    counters["errors"],
                    run_id,
                ),
            )
            conn.execute(
                """
                UPDATE connectors
                SET last_status='ready', last_error=NULL, last_sync_at=now(),
                    updated_at=now()
                WHERE id=%s
                """,
                (connector_id,),
            )
            conn.commit()

    except Exception as exc:
        with connect() as conn:
            conn.execute(
                """
                UPDATE connector_sync_runs
                SET status='failed', items_seen=%s, items_changed=%s,
                    items_skipped=%s, error_count=%s,
                    error_message=%s, completed_at=now()
                WHERE id=%s
                """,
                (
                    counters["seen"],
                    counters["changed"],
                    counters["skipped"],
                    counters["errors"] + 1,
                    str(exc)[:4000],
                    run_id,
                ),
            )
            conn.execute(
                """
                UPDATE connectors
                SET last_status='failed', last_error=%s, last_sync_at=now(),
                    updated_at=now()
                WHERE id=%s
                """,
                (str(exc)[:4000], connector_id),
            )
            conn.commit()
        raise
