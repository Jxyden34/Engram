import json
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import notifications as notices
from app.database import connect, project_scope, DEFAULT_PROJECT_ID
from app.security import hash_password


def test_notification_sources_receipts_resolution_and_project_isolation():
    from app.main import app
    name = "notify-" + uuid4().hex
    with connect() as conn:
        users = [str(conn.execute(
            "INSERT INTO users(username,password_hash,is_admin) VALUES (%s,%s,true) RETURNING id",
            (name + str(i), hash_password(name))).fetchone()["id"]) for i in range(2)]
        projects = [str(conn.execute("INSERT INTO projects(slug,name) VALUES (%s,'Notifications test') RETURNING id",
                                    (name + str(i),)).fetchone()["id"]) for i in range(2)]
        conn.commit()
    try:
        with project_scope(projects[0]), connect() as conn:
            memory = conn.execute("""
                INSERT INTO memories(title,content,importance,created_by,updated_by)
                VALUES ('Important fact','Updated private content',9,'test','test') RETURNING id
            """).fetchone()["id"]
            conn.execute("INSERT INTO memory_versions(memory_id,version_no,snapshot,actor) VALUES (%s,1,%s::jsonb,'test')",
                         (memory, json.dumps({"title": "Important fact", "content": "Old content"})))
            conn.execute("""
                INSERT INTO memories(title,content,memory_type,created_by,updated_by,updated_at)
                VALUES ('Credential notes','Never include this secret in notifications','credential','test','test',now()-interval '181 days')
            """)
            connector = conn.execute("""
                INSERT INTO connectors(connector_type,name,created_by,last_status)
                VALUES ('github','Private connector','test','failed') RETURNING id
            """).fetchone()["id"]
            doc = conn.execute("""
                INSERT INTO documents(filename,object_key,byte_size,sha256,uploaded_by,status)
                VALUES ('test.txt',%s,1,'test','test','ready') RETURNING id
            """, (name,)).fetchone()["id"]
            job = conn.execute("INSERT INTO document_memory_jobs(document_id,requested_by) VALUES (%s,'test') RETURNING id",
                               (doc,)).fetchone()["id"]
            conn.execute("""
                INSERT INTO document_candidate_memories(job_id,document_id,title,content,nearest_memory_id,comparison,created_at)
                VALUES (%s,%s,'Candidate','Private conflict',%s,'conflicts',now()-interval '8 days')
            """, (job, doc, memory))
            conn.commit()
        with project_scope(projects[0]):
            from app import telegram_notifications as telegram
            notices.refresh()
            notices.refresh()
            with patch.object(telegram, "settings", return_value=type("Config", (), {
                "telegram_bot_token": "fixture", "public_origin": "https://engram.invalid"
            })()):
                telegram.configure(telegram.TelegramSettings(enabled=True, chat_id="123"))
                with patch.object(telegram, "send", side_effect=HTTPException(status_code=502)) as failed:
                    telegram.deliver()
                    assert failed.call_count == 5
                    telegram.deliver()
                    assert failed.call_count == 5, "Backoff must prevent an immediate retry"
                with connect() as conn:
                    conn.execute("UPDATE notification_deliveries SET next_attempt_at=now()")
                    conn.commit()
                with patch.object(telegram, "send") as send:
                    telegram.deliver()
                    assert send.call_count == 5
                    telegram.deliver()
                    assert send.call_count == 5
            inbox = notices.inbox(users[0])
            assert {n["kind"] for n in inbox["items"]} == {
                "connector_failure", "important_conflict", "important_update", "stale_credentials", "unresolved_candidates"
            }
            assert inbox["unread"] == 5
            assert "Private" not in json.dumps(inbox, default=str)
            notification = next(n for n in inbox["items"] if n["kind"] == "connector_failure")
            notices.mark(str(notification["id"]), users[0], dismiss=True)
            notices.refresh()
            assert notices.inbox(users[0])["unread"] == 4
            assert notices.inbox(users[1])["unread"] == 5
            with connect() as conn:
                conn.execute("UPDATE connectors SET last_status='ready' WHERE id=%s", (connector,))
                conn.commit()
            notices.refresh()
            assert not any(n["kind"] == "connector_failure" for n in notices.inbox(users[1])["items"])
            with connect() as conn:
                conn.execute("UPDATE connectors SET last_status='failed' WHERE id=%s", (connector,))
                conn.commit()
            notices.refresh()
            reopened = next(n for n in notices.inbox(users[0])["items"] if n["kind"] == "connector_failure")
            assert reopened["generation"] == 2 and reopened["read_at"] is None
        with project_scope(projects[1]):
            notices.refresh()
            assert notices.inbox(users[0]) == {"items": [], "unread": 0}
            with pytest.raises(HTTPException) as error:
                notices.mark(str(notification["id"]), users[0])
            assert error.value.status_code == 404
        client = TestClient(app, base_url="http://localhost")
        assert client.get("/api/v1/notifications").status_code == 401
        client.post("/api/v1/auth/login", json={"username": name + "0", "password": name})
        result = client.get("/api/v1/notifications", headers={"X-Engram-Project": projects[0]})
        assert result.status_code == 200 and result.json()["unread"] == 5
        assert client.get("/api/v1/notifications", headers={"X-Engram-Project": projects[1]}).json()["items"] == []
    finally:
        for project in projects:
            with project_scope(project), connect() as conn:
                for table in ("notification_telegram", "notification_receipts", "notifications", "document_candidate_memories",
                              "document_memory_jobs", "documents", "connector_sync_runs", "connectors",
                              "memory_versions", "memories"):
                    conn.execute("DELETE FROM " + table)
                conn.commit()
        with connect() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id=ANY(%s::uuid[])", (users,))
            conn.execute("DELETE FROM users WHERE id=ANY(%s::uuid[])", (users,))
            conn.execute("DELETE FROM projects WHERE id=ANY(%s::uuid[])", (projects,))
            conn.execute("DELETE FROM audit_log WHERE actor=%s", ("user:" + name + "0",))
            conn.commit()


def test_backup_notifications_are_generic_and_only_in_personal_project():
    class Result:
        def __iter__(self):
            return iter([])
        def fetchone(self):
            return {"n": 0}

    class EmptyProject:
        def execute(self, *args):
            return Result()

    with patch.object(notices.disaster_recovery, "summary", return_value={"checks": [
        {"key": "postgres", "label": "PostgreSQL backup", "status": "critical", "detail": "No fresh verified PostgreSQL backup"},
        {"key": "objects", "label": "Object backup", "status": "healthy", "detail": "Verified"},
    ]}):
        with project_scope(DEFAULT_PROJECT_ID):
            items = notices.collect(EmptyProject())
            assert len(items) == 1 and items[0]["kind"] == "backup_failure"
        with project_scope(str(uuid4())):
            assert notices.collect(EmptyProject()) == []
