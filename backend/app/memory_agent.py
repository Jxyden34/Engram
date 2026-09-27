import json

from fastapi import HTTPException

from app.database import connect, current_project_id, project_job, project_scope


def scan() -> dict:
    """Create suggestions inside the active project; never change memories."""
    counts = {}
    with connect() as conn:
        counts["missing_provenance"] = conn.execute("""
            INSERT INTO agent_proposals(proposal_type, memory_id, reason, evidence)
            SELECT 'missing_provenance', id,
                   'Imported memory has no source reference; review its provenance.',
                   jsonb_build_object('source_type', source_type)
            FROM memories
            WHERE deleted_at IS NULL AND source_type <> 'manual' AND source_ref IS NULL
            ON CONFLICT DO NOTHING
            RETURNING id
        """).rowcount
        counts["stale"] = conn.execute("""
            INSERT INTO agent_proposals(proposal_type, memory_id, reason, evidence)
            SELECT 'stale', id,
                   'Memory has not been updated for two years; check whether it is still true.',
                   jsonb_build_object('updated_at', updated_at)
            FROM memories
            WHERE deleted_at IS NULL AND valid_to IS NULL
              AND updated_at < now() - interval '2 years'
            ON CONFLICT DO NOTHING
            RETURNING id
        """).rowcount
        counts["low_confidence"] = conn.execute("""
            INSERT INTO agent_proposals(proposal_type, memory_id, reason, evidence)
            SELECT 'low_confidence', id,
                   'This memory has low confidence; check the original source before relying on it.',
                   jsonb_build_object('confidence', confidence)
            FROM memories
            WHERE deleted_at IS NULL AND confidence < 0.5
            ON CONFLICT DO NOTHING
            RETURNING id
        """).rowcount
        counts["conflict"] = conn.execute("""
            INSERT INTO agent_proposals(proposal_type, memory_id, reason, evidence)
            SELECT DISTINCT ON (nearest_memory_id) 'conflict', nearest_memory_id,
                   'An imported candidate conflicts with this memory; review it in Memory Inbox.',
                   jsonb_build_object('candidate_id', id)
            FROM candidate_memories
            WHERE status='pending' AND comparison='conflicts' AND nearest_memory_id IS NOT NULL
            ORDER BY nearest_memory_id, created_at DESC
            ON CONFLICT DO NOTHING
            RETURNING id
        """).rowcount
        counts["conflict"] += conn.execute("""
            INSERT INTO agent_proposals(proposal_type, memory_id, reason, evidence)
            SELECT DISTINCT ON (nearest_memory_id) 'conflict', nearest_memory_id,
                   'A document candidate conflicts with this memory; review it in Memory Inbox.',
                   jsonb_build_object('candidate_id', id, 'source', 'document')
            FROM document_candidate_memories
            WHERE status='pending' AND comparison='conflicts' AND nearest_memory_id IS NOT NULL
            ORDER BY nearest_memory_id, created_at DESC
            ON CONFLICT DO NOTHING
            RETURNING id
        """).rowcount
        counts["duplicate"] = conn.execute("""
            WITH pairs AS (
                SELECT m.id AS memory_id, n.id AS related_memory_id,
                       1 - (m.embedding <=> n.embedding) AS similarity
                FROM memories m
                CROSS JOIN LATERAL (
                    SELECT id, embedding FROM memories n
                    WHERE n.id > m.id AND n.deleted_at IS NULL AND n.embedding IS NOT NULL
                    ORDER BY n.embedding <=> m.embedding LIMIT 1
                ) n
                WHERE m.deleted_at IS NULL AND m.embedding IS NOT NULL
                ORDER BY m.updated_at DESC LIMIT 500
            )
            INSERT INTO agent_proposals(proposal_type, memory_id, related_memory_id, reason, evidence)
            SELECT 'duplicate', memory_id, related_memory_id,
                   'These memories are semantically similar; review before consolidating.',
                   jsonb_build_object('similarity', similarity)
            FROM pairs WHERE similarity >= 0.94
            ON CONFLICT DO NOTHING
            RETURNING id
        """).rowcount
        conn.commit()
    return {"created": counts, "total": sum(counts.values())}


def list_proposals(status: str = "pending", limit: int = 100) -> list[dict]:
    if status not in {"pending", "dismissed"}:
        raise HTTPException(status_code=422, detail="Invalid proposal status")
    with connect() as conn:
        rows = conn.execute("""
            SELECT p.id, p.proposal_type, p.memory_id, m.title AS memory_title,
                   p.related_memory_id, r.title AS related_title,
                   p.reason, p.evidence, p.status, p.created_at, p.reviewed_at
            FROM agent_proposals p
            JOIN memories m ON m.id=p.memory_id
            LEFT JOIN memories r ON r.id=p.related_memory_id
            WHERE p.status=%s ORDER BY p.created_at DESC LIMIT %s
        """, (status, max(1, min(limit, 200)))).fetchall()
    return [dict(row) for row in rows]


def dismiss(proposal_id: str, actor: str) -> dict:
    with connect() as conn:
        row = conn.execute("""
            UPDATE agent_proposals SET status='dismissed', reviewed_at=now(), reviewed_by=%s
            WHERE id=%s AND status='pending' RETURNING id, status, reviewed_at
        """, (actor, proposal_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pending proposal not found")
        conn.commit()
    return dict(row)


def create_run(trigger_type: str) -> dict:
    with connect() as conn:
        row = conn.execute("""
            INSERT INTO agent_scan_runs(trigger_type) VALUES (%s)
            RETURNING id, trigger_type, status, created_at
        """, (trigger_type,)).fetchone()
        conn.commit()
    return dict(row)


def run_scan(run_id: str) -> dict:
    with connect() as conn:
        row = conn.execute("""
            UPDATE agent_scan_runs SET status='running', started_at=now()
            WHERE id=%s AND status='queued' RETURNING id
        """, (run_id,)).fetchone()
        if not row:
            raise ValueError("Queued agent scan not found in this project")
        conn.commit()
    try:
        result = scan()
    except Exception as exc:
        with connect() as conn:
            conn.execute("""
                UPDATE agent_scan_runs
                SET status='failed', error_message=%s, completed_at=now()
                WHERE id=%s
            """, (str(exc)[:1000], run_id))
            conn.commit()
        raise
    with connect() as conn:
        conn.execute("""
            UPDATE agent_scan_runs
            SET status='completed', result=%s::jsonb, completed_at=now()
            WHERE id=%s
        """, (json.dumps(result), run_id))
        conn.commit()
    return result


@project_job
def run_scheduled_scan(run_id: str):
    return run_scan(run_id)


def list_runs(limit: int = 20) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("""
            SELECT id, trigger_type, status, result, error_message,
                   created_at, started_at, completed_at
            FROM agent_scan_runs ORDER BY created_at DESC LIMIT %s
        """, (max(1, min(limit, 100)),)).fetchall()
    return [dict(row) for row in rows]


def get_schedule() -> dict:
    with connect() as conn:
        row = conn.execute("""
            SELECT enabled, interval_hours, next_scan_at, updated_at
            FROM agent_scan_schedules WHERE project_id=%s
        """, (current_project_id(),)).fetchone()
    return dict(row) if row else {"enabled": False, "interval_hours": 24, "next_scan_at": None}


def set_schedule(enabled: bool, interval_hours: int) -> dict:
    with connect() as conn:
        row = conn.execute("""
            INSERT INTO agent_scan_schedules(project_id, enabled, interval_hours, next_scan_at)
            VALUES (%s, %s, %s,
                    CASE WHEN %s THEN now() + (%s || ' hours')::interval ELSE NULL END)
            ON CONFLICT (project_id) DO UPDATE
            SET enabled=EXCLUDED.enabled, interval_hours=EXCLUDED.interval_hours,
                next_scan_at=EXCLUDED.next_scan_at, updated_at=now()
            RETURNING enabled, interval_hours, next_scan_at, updated_at
        """, (current_project_id(), enabled, interval_hours, enabled, interval_hours)).fetchone()
        conn.commit()
    return dict(row)


def queue_due_scans() -> int:
    with connect() as conn:
        project_ids = [str(row["id"]) for row in conn.execute("SELECT id FROM projects")]
    queued = 0
    for project_id in project_ids:
        with project_scope(project_id):
            with connect() as conn:
                schedule = conn.execute("""
                    SELECT interval_hours FROM agent_scan_schedules
                    WHERE project_id=%s AND enabled AND next_scan_at <= now()
                    FOR UPDATE SKIP LOCKED
                """, (project_id,)).fetchone()
                if not schedule:
                    continue
                run = conn.execute("""
                    INSERT INTO agent_scan_runs(trigger_type) VALUES ('scheduled') RETURNING id
                """).fetchone()
                conn.execute("""
                    UPDATE agent_scan_schedules
                    SET next_scan_at=now() + (interval_hours || ' hours')::interval,
                        updated_at=now()
                    WHERE project_id=%s
                """, (project_id,))
                conn.commit()
            try:
                from app.connectors import queue
                queue().enqueue(
                    "app.memory_agent.run_scheduled_scan", str(run["id"]),
                    job_timeout="30m", meta={"project_id": project_id},
                )
                queued += 1
            except Exception as exc:
                with connect() as conn:
                    conn.execute("""
                        UPDATE agent_scan_runs
                        SET status='failed', error_message=%s, completed_at=now()
                        WHERE id=%s
                    """, (str(exc)[:1000], run["id"]))
                    conn.commit()
                raise
    return queued
