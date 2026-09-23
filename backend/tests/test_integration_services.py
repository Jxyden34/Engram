from uuid import uuid4

from redis import Redis

from app.config import settings
from app.database import connect


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
