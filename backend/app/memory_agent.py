from fastapi import HTTPException

from app.database import connect


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
