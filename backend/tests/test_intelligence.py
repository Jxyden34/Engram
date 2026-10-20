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


def test_ask_hybrid_filters_candidates_before_limits_and_preserves_project_scope(monkeypatch):
    from app import ask
    from app.database import project_scope

    token = "filter" + uuid4().hex
    vector = "[" + ",".join(["1"] + ["0"] * 383) + "]"
    monkeypatch.setattr(intelligence, "embed_literal", lambda _: vector)
    monkeypatch.setattr(ask, "_ollama_json", lambda *_args, **_kwargs: {"claims": [], "insufficient": True})
    with connect() as conn:
        projects = [str(conn.execute("INSERT INTO projects(slug,name) VALUES (%s,'Retrieval filters') RETURNING id",
                    (token + suffix,)).fetchone()["id"]) for suffix in ("a", "b")]
        conn.commit()
    try:
        with project_scope(projects[0]):
            with connect() as conn:
                semantic = str(conn.execute("""INSERT INTO memories(title,content,memory_type,embedding,updated_at,created_by,updated_by)
                    VALUES (%s,'Start boundary','decision',%s::vector,'2026-09-30T00:00:00Z','test','test') RETURNING id""",
                    (token, vector)).fetchone()["id"])
                lexical = str(conn.execute("""INSERT INTO memories(title,content,memory_type,updated_at,created_by,updated_by)
                    VALUES (%s,'End boundary without embedding','decision','2026-09-30T23:59:59.999999Z','test','test') RETURNING id""",
                    (token,)).fetchone()["id"])
                # More excluded near-neighbours than the semantic candidate limit.
                conn.execute("""INSERT INTO memories(title,content,memory_type,embedding,updated_at,created_by,updated_by)
                    SELECT %s,'Outside date window','decision',%s::vector,'2026-10-01T00:00:00Z','test','test'
                    FROM generate_series(1,60)""", (token, vector))
                conn.execute("""INSERT INTO memories(title,content,memory_type,embedding,updated_at,valid_to,deleted_at,created_by,updated_by)
                    VALUES (%s,'Wrong type','general',%s::vector,'2026-09-30',NULL,NULL,'test','test'),
                           (%s,'Historical','decision',%s::vector,'2026-09-30','2026-09-29',NULL,'test','test'),
                           (%s,'Deleted','decision',%s::vector,'2026-09-30',NULL,now(),'test','test'),
                           (%s,'Before start','decision',%s::vector,'2026-09-29T23:59:59.999999Z',NULL,NULL,'test','test')""",
                    (token, vector, token, vector, token, vector, token, vector))
                conn.commit()
        with project_scope(projects[1]):
            with connect() as conn:
                foreign = str(conn.execute("""INSERT INTO memories(title,content,memory_type,embedding,updated_at,created_by,updated_by)
                    VALUES (%s,'Other project','decision',%s::vector,'2026-09-30','test','test') RETURNING id""",
                    (token, vector)).fetchone()["id"])
                conn.commit()
        with project_scope(projects[0]):
            # 'When' must not make Ask include historical memories implicitly.
            result = ask.answer("When " + token, "decision", "2026-09-30", "2026-09-30")
            assert {str(row["id"]) for row in result["sources"]} == {semantic, lexical}
            assert result["project_id"] == projects[0]
            assert result["filters"]["since"] == "2026-09-30"
        with project_scope(projects[1]):
            result = ask.answer(token, "decision", "2026-09-30", "2026-09-30")
            assert [str(row["id"]) for row in result["sources"]] == [foreign]
    finally:
        for project in projects:
            with project_scope(project):
                with connect() as conn:
                    conn.execute("DELETE FROM memories WHERE project_id=%s", (project,))
                    conn.commit()
        with connect() as conn:
            conn.execute("DELETE FROM projects WHERE id=ANY(%s::uuid[])", (projects,))
            conn.commit()
