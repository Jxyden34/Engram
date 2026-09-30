from datetime import datetime, timezone
from uuid import uuid4

from app import intelligence
from app.database import connect


def test_query_planner_keeps_history_and_relationships_distinct():
    assert intelligence.plan_query("When did I use the old server?")["include_historical"] is True
    assert intelligence.plan_query("Who is connected to Atlas?")["intent"] == "relationship"
    assert intelligence.plan_query("What is current on Atlas?")["intent"] == "current"


def test_context_is_bounded_and_preserves_source_labels(monkeypatch):
    row = {"id": uuid4(), "title": "Router", "content": "A" * 3000, "result_type": "memory",
           "source_type": "manual", "source_ref": "notebook", "temporal_state": "current",
           "retrieval_score": 0.9, "match_reasons": ["text match"]}
    monkeypatch.setattr(intelligence, "search_memories", lambda *_: [row])
    result = intelligence.build_context("current router", 500)
    assert len(result["context"]) <= 500
    assert "notebook" in result["context"]
    assert result["items"][0]["truncated"] is True
    assert result["matches"][0]["match_reasons"] == ["text match"]


def test_hybrid_retrieval_and_reviewed_resolution(monkeypatch):
    """Exercise real PostgreSQL candidate selection, lexical fallback and history."""
    token = "engram" + uuid4().hex
    vector = "[" + ",".join(["1"] + ["0"] * 383) + "]"
    monkeypatch.setattr(intelligence, "embed_literal", lambda _query: vector)
    with connect() as conn:
        first = conn.execute("""INSERT INTO memories(title,content,embedding,created_by,updated_by)
            VALUES (%s,%s,%s::vector,'test','test') RETURNING id""",
            (token + " original", "The service runs on node one", vector)).fetchone()["id"]
        second = conn.execute("""INSERT INTO memories(title,content,embedding,created_by,updated_by)
            VALUES (%s,%s,%s::vector,'test','test') RETURNING id""",
            (token + " updated", "The service runs on node two", vector)).fetchone()["id"]
        lexical = conn.execute("""INSERT INTO memories(title,content,created_by,updated_by)
            VALUES (%s,'Lexical-only fact','test','test') RETURNING id""",
            (token + " lexical",)).fetchone()["id"]
        conn.commit()
    try:
        results = intelligence.search_memories(token, 20)
        assert str(lexical) in {str(item["id"]) for item in results}
        assert all("retrieval_score" in item and "match_reasons" in item for item in results)
        candidates = intelligence.candidate_conflicts(30)
        assert any({str(item["first_id"]), str(item["second_id"])} == {str(first), str(second)} for item in candidates)
        comparison = intelligence.compare_memories(str(first), str(second))
        assert comparison["status"] == "needs_human_review"
        resolved = intelligence.resolve_conflict(str(first), str(second), str(second), "test", "Verified current host from new source")
        assert resolved["historical_id"] == str(first)
        with connect() as conn:
            old = conn.execute("SELECT valid_to,deleted_at FROM memories WHERE id=%s", (first,)).fetchone()
            assert old["valid_to"] <= datetime.now(timezone.utc)
            assert old["deleted_at"] is None
            assert conn.execute("SELECT 1 FROM memory_versions WHERE memory_id=%s", (first,)).fetchone()
            assert conn.execute("SELECT 1 FROM memory_relations WHERE from_memory_id=%s AND to_memory_id=%s AND relation_type='superseded_by'", (first, second)).fetchone()
    finally:
        with connect() as conn:
            conn.execute("DELETE FROM memory_relations WHERE from_memory_id=ANY(%s::uuid[]) OR to_memory_id=ANY(%s::uuid[])", ([first, second], [first, second]))
            conn.execute("DELETE FROM memory_versions WHERE memory_id=ANY(%s::uuid[])", ([first, second, lexical],))
            conn.execute("DELETE FROM memories WHERE id=ANY(%s::uuid[])", ([first, second, lexical],))
            conn.commit()
