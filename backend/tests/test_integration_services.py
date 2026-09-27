from uuid import uuid4
import json
from unittest.mock import patch

from redis import Redis
from fastapi import HTTPException
import pytest

from app.config import settings
from app.database import connect, project_scope
from app.memory_agent import (
    scan, list_proposals, list_runs, get_schedule, set_schedule, queue_due_scans, run_scan,
)
from app import oauth
from app.projects import resolve_project
from app.security import Principal


def test_postgres_connectivity_and_schema():
    with connect() as conn:
        row = conn.execute("SELECT 1 AS value").fetchone()
        assert row["value"] == 1

        vector = conn.execute(
            """
            SELECT extname
            FROM pg_extension
            WHERE extname = 'vector'
            """
        ).fetchone()

        assert vector is not None
        assert vector["extname"] == "vector"

        rows = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        ).fetchall()

        tables = {row["table_name"] for row in rows}

        assert "memories" in tables
        assert "documents" in tables


def test_redis_round_trip():
    client = Redis.from_url(
        settings().redis_url,
        decode_responses=True,
    )

    key = f"engram:ci:{uuid4()}"

    try:
        assert client.ping() is True
        assert client.set(key, "integration-ok", ex=30) is True
        assert client.get(key) == "integration-ok"
    finally:
        client.delete(key)


def test_project_rls_and_agent_proposals():
    slug = f"ci-{uuid4().hex[:12]}"
    with connect() as conn:
        assert conn.execute("SELECT current_user AS role").fetchone()["role"] == "engram_runtime"
        project_id = str(conn.execute(
            "INSERT INTO projects(slug,name) VALUES (%s,'CI project') RETURNING id", (slug,)
        ).fetchone()["id"])
        entity_id = str(conn.execute(
            "INSERT INTO entities(name,normalized_name,created_by,updated_by) VALUES (%s,%s,'test','test') RETURNING id",
            (slug, slug),
        ).fetchone()["id"])
        conn.commit()
    key = Principal("test", None, None, False, {"memory:read"}, "api_key", project_id)
    assert resolve_project(key, None) == project_id
    with pytest.raises(HTTPException) as exc:
        resolve_project(key, "00000000-0000-0000-0000-000000000001")
    assert exc.value.status_code == 403
    with project_scope(project_id):
        with connect() as conn:
            project_entity_id = str(conn.execute(
                "INSERT INTO entities(name,normalized_name,created_by,updated_by) VALUES (%s,%s,'test','test') RETURNING id",
                (slug, slug),
            ).fetchone()["id"])
            memory_id = str(conn.execute("""
                INSERT INTO memories(title, content, source_type, confidence, created_by, updated_by)
                VALUES ('CI source', 'Project-only content', 'document_import', 0.4, 'test', 'test')
                RETURNING id
            """).fetchone()["id"])
            conn.commit()
        created = scan()["created"]
        assert created["missing_provenance"] == 1
        assert created["low_confidence"] == 1
        assert any(str(p["memory_id"]) == memory_id for p in list_proposals())
    with connect() as conn:
        assert conn.execute("SELECT id FROM memories WHERE id=%s", (memory_id,)).fetchone() is None
        assert conn.execute("SELECT id FROM agent_proposals WHERE memory_id=%s", (memory_id,)).fetchone() is None
    with project_scope(project_id):
        with connect() as conn:
            conn.execute("DELETE FROM agent_proposals WHERE memory_id=%s", (memory_id,))
            conn.execute("DELETE FROM memories WHERE id=%s", (memory_id,))
            conn.execute("DELETE FROM entities WHERE id=%s", (project_entity_id,))
            conn.commit()
    with connect() as conn:
        conn.execute("DELETE FROM entities WHERE id=%s", (entity_id,))
        conn.execute("DELETE FROM projects WHERE id=%s", (project_id,))
        conn.commit()


def test_oauth_tokens_stay_in_consented_project():
    slug = f"oauth-{uuid4().hex[:12]}"
    client_id = f"mb_client_{uuid4().hex}"
    with connect() as conn:
        project_id = str(conn.execute(
            "INSERT INTO projects(slug,name) VALUES (%s,'OAuth CI') RETURNING id", (slug,)
        ).fetchone()["id"])
        user_id = str(conn.execute(
            "INSERT INTO users(username,password_hash) VALUES (%s,'ci') RETURNING id", (slug,)
        ).fetchone()["id"])
        conn.execute("""
            INSERT INTO oauth_clients(client_id,client_name,registration_type,redirect_uris,
                                      allowed_scopes,created_by)
            VALUES (%s,'CI client','static',%s,%s,'ci')
        """, (client_id, ["http://localhost/callback"], ["mcp:use", "memory:read"]))
        conn.commit()
    verifier = "v" * 43
    with project_scope(project_id):
        code = oauth.create_authorization_code(
            client_id, user_id, "http://localhost/callback",
            ["mcp:use", "memory:read"], oauth.mcp_resource(), oauth._pkce_s256(verifier),
        )
    response = oauth.exchange_authorization_code({
        "code": code, "client_id": client_id, "redirect_uri": "http://localhost/callback",
        "code_verifier": verifier, "resource": oauth.mcp_resource(),
    })
    tokens = json.loads(response.body)
    principal = oauth.oauth_access_token_principal(tokens["access_token"], oauth.mcp_resource())
    assert principal.project_id == project_id
    assert resolve_project(principal, project_id) == project_id
    with pytest.raises(HTTPException) as exc:
        resolve_project(principal, "00000000-0000-0000-0000-000000000001")
    assert exc.value.status_code == 403
    renewed = oauth.exchange_refresh_token({
        "refresh_token": tokens["refresh_token"], "client_id": client_id,
        "resource": oauth.mcp_resource(),
    })
    renewed_tokens = json.loads(renewed.body)
    assert oauth.oauth_access_token_principal(
        renewed_tokens["access_token"], oauth.mcp_resource()
    ).project_id == project_id
    with connect() as conn:
        rows = conn.execute("""
            SELECT DISTINCT project_id FROM oauth_access_tokens WHERE client_id=%s
        """, (client_id,)).fetchall()
        assert [str(row["project_id"]) for row in rows] == [project_id]
        conn.execute("DELETE FROM oauth_access_tokens WHERE client_id=%s", (client_id,))
        conn.execute("DELETE FROM oauth_refresh_tokens WHERE client_id=%s", (client_id,))
        conn.execute("DELETE FROM oauth_authorization_codes WHERE client_id=%s", (client_id,))
        conn.execute("DELETE FROM oauth_consents WHERE client_id=%s", (client_id,))
        conn.execute("DELETE FROM oauth_clients WHERE client_id=%s", (client_id,))
        conn.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.execute("DELETE FROM projects WHERE id=%s", (project_id,))
        conn.commit()


def test_agent_schedule_queues_and_records_project_scan():
    slug = f"agent-{uuid4().hex[:12]}"
    with connect() as conn:
        project_id = str(conn.execute(
            "INSERT INTO projects(slug,name) VALUES (%s,'Agent CI') RETURNING id", (slug,)
        ).fetchone()["id"])
        conn.commit()
    with project_scope(project_id):
        with connect() as conn:
            memory_id = str(conn.execute("""
                INSERT INTO memories(title,content,source_type,created_by,updated_by)
                VALUES ('Agent CI','Check provenance','document_import','ci','ci') RETURNING id
            """).fetchone()["id"])
            conn.commit()
        assert set_schedule(True, 24)["enabled"] is True
        with connect() as conn:
            conn.execute("""
                UPDATE agent_scan_schedules SET next_scan_at=now() - interval '1 minute'
                WHERE project_id=%s
            """, (project_id,))
            conn.commit()
    with patch("app.connectors.queue") as mock_queue:
        assert queue_due_scans() == 1
        mock_queue.return_value.enqueue.assert_called_once()
        assert mock_queue.return_value.enqueue.call_args.kwargs["meta"] == {"project_id": project_id}
    with project_scope(project_id):
        runs = list_runs()
        assert len(runs) == 1 and runs[0]["status"] == "queued"
        assert run_scan(str(runs[0]["id"]))["created"]["missing_provenance"] == 1
        assert list_runs()[0]["status"] == "completed"
        assert get_schedule()["next_scan_at"] is not None
    assert list_runs() == []
    with project_scope(project_id):
        with connect() as conn:
            conn.execute("DELETE FROM agent_proposals WHERE memory_id=%s", (memory_id,))
            conn.execute("DELETE FROM agent_scan_runs WHERE project_id=%s", (project_id,))
            conn.execute("DELETE FROM agent_scan_schedules WHERE project_id=%s", (project_id,))
            conn.execute("DELETE FROM memories WHERE id=%s", (memory_id,))
            conn.commit()
    with connect() as conn:
        conn.execute("DELETE FROM projects WHERE id=%s", (project_id,))
        conn.commit()
