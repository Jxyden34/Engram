import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from redis import Redis
from rq import Queue

from app.chatgpt_import import _ollama_json
from app.config import settings
from app.database import connect
from app.embeddings import embed_literal
from app.util import json_text

KNOWLEDGE_SYSTEM = """Extract a knowledge graph from one durable memory.
Return ONLY JSON:
{
  "entities":[{"name":"canonical name","entity_type":"person|server|device|project|company|software|place|organisation|concept|other","description":"brief description","aliases":[]}],
  "relations":[{"from":"entity name","to":"entity name","relation_type":"short verb phrase","confidence":0.0}],
  "events":[{"title":"event title","description":"brief description","event_type":"deployment|upgrade|employment|education|travel|purchase|decision|milestone|incident|other","occurred_at":"ISO-8601 or null","ended_at":"ISO-8601 or null","importance":1,"confidence":0.0,"entity_names":[]}]
}
Use only supported facts. Do not invent dates. Relationship names must match extracted entities. Events are only things that happened or changed. Never extract secrets or authentication material."""


def queue():
    return Queue("document-ingest", connection=Redis.from_url(settings().redis_url))


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())[:300]


def _slug(value: str | None, default: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", (value or default).strip().lower()).strip("-")
    return (value or default)[:80]


def _dt(value: Any):
    if not value:
        return None
    try:
        s = str(value).strip()
        if len(s) == 10 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            s += "T00:00:00+00:00"
        parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def queue_memory_enrichment(memory_id: str, actor: str = "system:knowledge"):
    with connect() as conn:
        memory = conn.execute("SELECT id, updated_at FROM memories WHERE id=%s AND deleted_at IS NULL", (memory_id,)).fetchone()
        if not memory:
            return None
        row = conn.execute(
            """
            INSERT INTO knowledge_enrichment(memory_id,memory_updated_at,status,model_name,queued_at)
            VALUES (%s,%s,'queued',%s,now())
            ON CONFLICT (memory_id) DO UPDATE SET
              memory_updated_at=EXCLUDED.memory_updated_at,status='queued',model_name=EXCLUDED.model_name,
              error_message=NULL,queued_at=now()
            RETURNING *
            """,
            (memory_id, memory["updated_at"], settings().chat_model),
        ).fetchone()
        conn.commit()
    queue().enqueue("app.knowledge.enrich_memory_job", memory_id, actor, job_timeout="30m")
    return dict(row)


def queue_all(actor: str):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.id FROM memories m
            LEFT JOIN knowledge_enrichment k ON k.memory_id=m.id
            WHERE m.deleted_at IS NULL AND (m.valid_to IS NULL OR m.valid_to > now())
              AND (k.memory_id IS NULL OR k.memory_updated_at < m.updated_at OR k.status='failed')
            ORDER BY m.updated_at DESC
            """
        ).fetchall()
    count = 0
    for row in rows:
        if queue_memory_enrichment(str(row["id"]), actor):
            count += 1
    return {"queued": count}


def _upsert_entity(conn, item: dict[str, Any], owner_id: str | None, actor: str):
    name = str(item.get("name") or "").strip()[:300]
    if not name:
        return None
    entity_type = _slug(item.get("entity_type"), "other")
    description = str(item.get("description") or "").strip()[:2000] or None
    aliases = sorted({str(x).strip()[:300] for x in (item.get("aliases") or []) if str(x).strip()})[:30]
    vector = embed_literal(f"{name}\n{description or ''}")
    row = conn.execute(
        """
        INSERT INTO entities(owner_id,name,normalized_name,entity_type,description,aliases,embedding,created_by,updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s::vector,%s,%s)
        ON CONFLICT (normalized_name,entity_type) DO UPDATE SET
          description=COALESCE(EXCLUDED.description,entities.description),
          aliases=(SELECT ARRAY(SELECT DISTINCT x FROM unnest(entities.aliases || EXCLUDED.aliases) x)),
          embedding=EXCLUDED.embedding,updated_by=EXCLUDED.updated_by,updated_at=now()
        RETURNING *
        """,
        (owner_id, name, _norm(name), entity_type, description, aliases, vector, actor, actor),
    ).fetchone()
    return dict(row)


def enrich_memory_job(memory_id: str, actor: str = "system:knowledge"):
    with connect() as conn:
        memory = conn.execute(
            """
            SELECT id,owner_id,title,content,memory_type,tags,source_type,source_ref,
                   valid_from,valid_to,updated_at
            FROM memories WHERE id=%s AND deleted_at IS NULL
            """,
            (memory_id,),
        ).fetchone()
        if not memory:
            return
        conn.execute("UPDATE knowledge_enrichment SET status='processing',started_at=now(),error_message=NULL WHERE memory_id=%s", (memory_id,))
        conn.commit()

    try:
        data = _ollama_json(KNOWLEDGE_SYSTEM, f"""Title: {memory['title']}
Type: {memory['memory_type']}
Tags: {', '.join(memory['tags'] or [])}
Valid from: {memory['valid_from'] or 'unknown'}
Valid to: {memory['valid_to'] or 'current/unknown'}
Content:\n{memory['content']}""")
        entities = data.get("entities", []) if isinstance(data, dict) else []
        relations = data.get("relations", []) if isinstance(data, dict) else []
        events = data.get("events", []) if isinstance(data, dict) else []

        with connect() as conn:
            conn.execute("DELETE FROM memory_entity_links WHERE memory_id=%s", (memory_id,))
            conn.execute("DELETE FROM entity_relations WHERE source_memory_id=%s", (memory_id,))
            conn.execute("DELETE FROM events WHERE source_memory_id=%s", (memory_id,))
            entity_map = {}
            for raw in entities[:50] if isinstance(entities, list) else []:
                if not isinstance(raw, dict):
                    continue
                entity = _upsert_entity(conn, raw, str(memory["owner_id"]) if memory["owner_id"] else None, actor)
                if entity:
                    entity_map[_norm(entity["name"])] = entity
                    conn.execute("INSERT INTO memory_entity_links(memory_id,entity_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (memory_id, entity["id"]))

            relation_count = 0
            for rel in relations[:100] if isinstance(relations, list) else []:
                if not isinstance(rel, dict):
                    continue
                left = entity_map.get(_norm(str(rel.get("from") or "")))
                right = entity_map.get(_norm(str(rel.get("to") or "")))
                if not left or not right or left["id"] == right["id"]:
                    continue
                try:
                    confidence = max(0.0, min(1.0, float(rel.get("confidence", 0.9))))
                except Exception:
                    confidence = 0.9
                conn.execute(
                    """
                    INSERT INTO entity_relations(from_entity_id,to_entity_id,relation_type,confidence,source_memory_id,valid_from,valid_to,created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (from_entity_id,to_entity_id,relation_type,source_memory_id)
                    WHERE source_memory_id IS NOT NULL DO UPDATE SET confidence=EXCLUDED.confidence,valid_from=EXCLUDED.valid_from,valid_to=EXCLUDED.valid_to,updated_at=now()
                    """,
                    (left["id"], right["id"], _slug(rel.get("relation_type"), "related-to"), confidence, memory_id, memory["valid_from"], memory["valid_to"], actor),
                )
                relation_count += 1

            event_count = 0
            for event in events[:40] if isinstance(events, list) else []:
                if not isinstance(event, dict):
                    continue
                title = str(event.get("title") or "").strip()[:300]
                if not title:
                    continue
                description = str(event.get("description") or "").strip()[:5000] or None
                occurred = _dt(event.get("occurred_at"))
                ended = _dt(event.get("ended_at"))
                try: importance = max(1, min(10, int(event.get("importance", 5))))
                except Exception: importance = 5
                try: confidence = max(0.0, min(1.0, float(event.get("confidence", 0.85))))
                except Exception: confidence = 0.85
                vector = embed_literal(f"{title}\n{description or ''}")
                row = conn.execute(
                    """
                    INSERT INTO events(owner_id,title,description,event_type,occurred_at,ended_at,importance,confidence,source_type,source_ref,source_memory_id,embedding,created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'memory',%s,%s,%s::vector,%s)
                    ON CONFLICT (source_memory_id,lower(title),coalesce(occurred_at,'1970-01-01'::timestamptz))
                    WHERE source_memory_id IS NOT NULL DO UPDATE SET description=EXCLUDED.description,event_type=EXCLUDED.event_type,ended_at=EXCLUDED.ended_at,importance=EXCLUDED.importance,confidence=EXCLUDED.confidence,embedding=EXCLUDED.embedding,updated_at=now()
                    RETURNING id
                    """,
                    (memory["owner_id"], title, description, _slug(event.get("event_type"), "event"), occurred, ended, importance, confidence, str(memory_id), memory_id, vector, actor),
                ).fetchone()
                if row:
                    event_count += 1
                    for name in event.get("entity_names") or []:
                        entity = entity_map.get(_norm(str(name)))
                        if entity:
                            conn.execute("INSERT INTO event_entities(event_id,entity_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (row["id"], entity["id"]))

            conn.execute(
                """
                UPDATE knowledge_enrichment SET status='ready',memory_updated_at=%s,model_name=%s,
                  entity_count=%s,relation_count=%s,event_count=%s,completed_at=now(),error_message=NULL
                WHERE memory_id=%s
                """,
                (memory["updated_at"], settings().chat_model, len(entity_map), relation_count, event_count, memory_id),
            )
            conn.commit()
    except Exception as exc:
        with connect() as conn:
            conn.execute("UPDATE knowledge_enrichment SET status='failed',error_message=%s,completed_at=now() WHERE memory_id=%s", (str(exc)[:4000], memory_id))
            conn.commit()
        raise


def graph(limit: int = 60):
    limit = min(max(limit, 5), 120)
    with connect() as conn:
        nodes = [dict(r) for r in conn.execute(
            """
            SELECT e.id,e.name,e.entity_type,e.description,count(DISTINCT mel.memory_id) AS memory_count,count(DISTINCT er.id) AS relation_count
            FROM entities e LEFT JOIN memory_entity_links mel ON mel.entity_id=e.id
            LEFT JOIN entity_relations er ON er.from_entity_id=e.id OR er.to_entity_id=e.id
            GROUP BY e.id ORDER BY (count(DISTINCT mel.memory_id)+count(DISTINCT er.id)) DESC,e.updated_at DESC LIMIT %s
            """, (limit,)).fetchall()]
        ids = [r["id"] for r in nodes]
        edges = []
        if ids:
            edges = [dict(r) for r in conn.execute(
                """
                SELECT r.id,r.from_entity_id,r.to_entity_id,r.relation_type,r.confidence,a.name AS from_name,b.name AS to_name
                FROM entity_relations r JOIN entities a ON a.id=r.from_entity_id JOIN entities b ON b.id=r.to_entity_id
                WHERE r.from_entity_id=ANY(%s::uuid[]) AND r.to_entity_id=ANY(%s::uuid[]) ORDER BY r.confidence DESC LIMIT 300
                """, (ids, ids)).fetchall()]
    for n in nodes:
        n["memory_count"] = int(n["memory_count"] or 0); n["relation_count"] = int(n["relation_count"] or 0)
    for e in edges: e["confidence"] = float(e["confidence"])
    return {"nodes": nodes, "edges": edges}


def list_entities(limit: int = 150):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT e.id,e.name,e.entity_type,e.description,e.aliases,count(DISTINCT mel.memory_id) AS memory_count
            FROM entities e LEFT JOIN memory_entity_links mel ON mel.entity_id=e.id
            GROUP BY e.id ORDER BY count(DISTINCT mel.memory_id) DESC,e.updated_at DESC LIMIT %s
            """, (min(max(limit,1),250),)).fetchall()
    out=[]
    for row in rows:
        item=dict(row); item["memory_count"] = int(item["memory_count"] or 0); out.append(item)
    return out


def get_entity(entity_id: str):
    with connect() as conn:
        entity = conn.execute("SELECT * FROM entities WHERE id=%s", (entity_id,)).fetchone()
        if not entity: raise HTTPException(status_code=404, detail="Entity not found")
        memories = [dict(r) for r in conn.execute(
            """SELECT m.id,m.title,m.memory_type,m.importance,mel.role FROM memory_entity_links mel JOIN memories m ON m.id=mel.memory_id WHERE mel.entity_id=%s AND m.deleted_at IS NULL ORDER BY m.updated_at DESC LIMIT 100""", (entity_id,)).fetchall()]
        relations = [dict(r) for r in conn.execute(
            """SELECT r.id,r.relation_type,r.confidence,a.name AS from_name,b.name AS to_name FROM entity_relations r JOIN entities a ON a.id=r.from_entity_id JOIN entities b ON b.id=r.to_entity_id WHERE r.from_entity_id=%s OR r.to_entity_id=%s ORDER BY r.updated_at DESC LIMIT 150""", (entity_id,entity_id)).fetchall()]
    out=dict(entity); out["memories"]=memories
    for r in relations: r["confidence"] = float(r["confidence"])
    out["relations"]=relations
    return out


def create_entity(payload: dict[str, Any], actor: str, owner_id: str | None):
    with connect() as conn:
        row = _upsert_entity(conn, payload, owner_id, actor); conn.commit()
    if not row: raise HTTPException(status_code=400, detail="Entity name required")
    return row


def list_events(limit: int = 300):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT e.id,e.title,e.description,e.event_type,e.occurred_at,e.ended_at,e.importance,e.confidence,e.source_memory_id,e.created_at,
                   COALESCE(array_agg(DISTINCT en.name) FILTER (WHERE en.id IS NOT NULL),'{}') AS entities
            FROM events e LEFT JOIN event_entities ee ON ee.event_id=e.id LEFT JOIN entities en ON en.id=ee.entity_id
            GROUP BY e.id ORDER BY COALESCE(e.occurred_at,e.created_at) DESC LIMIT %s
            """, (min(max(limit,1),500),)).fetchall()
    out=[]
    for row in rows:
        item=dict(row); item["confidence"] = float(item["confidence"]); out.append(item)
    return out


def create_event(payload: dict[str, Any], actor: str, owner_id: str | None):
    title=str(payload.get("title") or "").strip()[:300]
    if not title: raise HTTPException(status_code=400, detail="Title required")
    description=str(payload.get("description") or "").strip() or None
    vector=embed_literal(f"{title}\n{description or ''}")
    with connect() as conn:
        row=conn.execute(
            """
            INSERT INTO events(owner_id,title,description,event_type,occurred_at,ended_at,importance,confidence,source_type,source_ref,metadata,embedding,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'manual',NULL,%s::jsonb,%s::vector,%s) RETURNING *
            """,
            (owner_id,title,description,_slug(payload.get("event_type"),"event"),payload.get("occurred_at"),payload.get("ended_at"),payload.get("importance",5),payload.get("confidence",1.0),json_text(payload.get("metadata",{})),vector,actor),
        ).fetchone(); conn.commit()
    return dict(row)
