import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import jwt
from fastapi import HTTPException
from redis import Redis
from rq import Queue

from app.config import settings
from app.database import connect
from app.documents import store_bytes


GITHUB_API_VERSION = "2026-03-10"

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
    }


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


def create_connector(data: dict[str, Any], actor: str, owner_id: str | None):
    connector_type = str(data.get("connector_type") or "").strip().lower()
    if connector_type != "github":
        raise HTTPException(status_code=400, detail="v2.1 currently supports connector_type=github")

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
    return dict(row)


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
        config = _validate_github_config(changes["config"])

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
    return dict(row)


def delete_connector(connector_id: str):
    with connect() as conn:
        row = conn.execute(
            "DELETE FROM connectors WHERE id=%s RETURNING id, name",
            (connector_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Connector not found")
        conn.commit()
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
    return [dict(row) for row in rows]


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
    )
    return dict(run)


def queue_due_connectors():
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
        source_type="github",
        source_ref=external_url,
        source_metadata={
            "connector_id": str(connector["id"]),
            "connector_name": connector["name"],
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
        if connector["connector_type"] != "github":
            raise RuntimeError(f"Unsupported connector type: {connector['connector_type']}")

        config = _validate_github_config(connector["config"])
        token = _installation_token(config["installation_id"])

        with _github_client(token) as client:
            repositories = _paginate(
                client,
                "/installation/repositories",
                limit=1000,
            )
            wanted = set(config["repositories"])
            if wanted:
                repositories = [
                    repo for repo in repositories
                    if repo["full_name"].lower() in wanted
                ]

            for repo in repositories:
                if counters["seen"] >= config["max_items_per_sync"]:
                    break
                try:
                    _sync_repo(client, dict(connector), run_id, repo, config, counters)
                except Exception:
                    counters["errors"] += 1

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
