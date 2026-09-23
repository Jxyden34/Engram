from uuid import uuid4

from redis import Redis

from app.config import settings
from app.database import connect, project_scope
from app.memory_agent import scan, list_proposals


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

    key = f"memorybank:ci:{uuid4()}"

    try:
        assert client.ping() is True
        assert client.set(key, "integration-ok", ex=30) is True
        assert client.get(key) == "integration-ok"
    finally:
        client.delete(key)


def test_project_rls_and_agent_proposals():
    slug = f"ci-{uuid4().hex[:12]}"
    with connect() as conn:
        assert conn.execute("SELECT current_user AS role").fetchone()["role"] == "memorybank_runtime"
        project_id = str(conn.execute(
            "INSERT INTO projects(slug,name) VALUES (%s,'CI project') RETURNING id", (slug,)
        ).fetchone()["id"])
        conn.commit()
    with project_scope(project_id):
        with connect() as conn:
            memory_id = str(conn.execute("""
                INSERT INTO memories(title, content, source_type, created_by, updated_by)
                VALUES ('CI source', 'Project-only content', 'document_import', 'test', 'test')
                RETURNING id
            """).fetchone()["id"])
            conn.commit()
        assert scan()["created"]["missing_provenance"] == 1
        assert any(p["memory_id"] == memory_id for p in list_proposals())
    with connect() as conn:
        assert conn.execute("SELECT id FROM memories WHERE id=%s", (memory_id,)).fetchone() is None
        assert conn.execute("SELECT id FROM agent_proposals WHERE memory_id=%s", (memory_id,)).fetchone() is None
    with project_scope(project_id):
        with connect() as conn:
            conn.execute("DELETE FROM agent_proposals WHERE memory_id=%s", (memory_id,))
            conn.execute("DELETE FROM memories WHERE id=%s", (memory_id,))
            conn.commit()
    with connect() as conn:
        conn.execute("DELETE FROM projects WHERE id=%s", (project_id,))
        conn.commit()
