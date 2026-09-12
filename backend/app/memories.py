from math import log
from typing import Any
from fastapi import HTTPException
from app.database import connect
from app.embeddings import embed_literal
from app.util import json_text

MEMORY_FIELDS = """
id, owner_id, title, content, memory_type, importance, confidence, tags,
source_type, source_ref, metadata, created_by, updated_by, created_at, updated_at,
valid_from, valid_to, supersedes_memory_id, source_trust, access_count, last_accessed_at
"""

MEMORY_SCORE_SQL = """
LEAST(1.50, GREATEST(0.0,
  (importance::float / 10.0) * confidence::float * source_trust::float
  * GREATEST(0.35, 1.0 / (1.0 + GREATEST(EXTRACT(EPOCH FROM (now() - updated_at)),0) / 31557600.0))
  * LEAST(1.20, 1.0 + ln(1.0 + access_count::float) * 0.05)
  * CASE WHEN valid_to IS NOT NULL AND valid_to <= now() THEN 0.45 ELSE 1.0 END
))
"""


def _default_source_trust(source_type: str | None) -> float:
    return {"manual":1.0,"chatgpt_import":0.92,"document_import":0.90,"api":0.88,"ai":0.75}.get((source_type or "").lower(),0.85)


def _score(row: dict[str, Any]) -> float:
    from datetime import datetime, timezone
    importance=float(row.get("importance") or 5)/10.0
    confidence=float(row.get("confidence") or 0)
    trust=float(row.get("source_trust") or 0.85)
    updated=row.get("updated_at")
    age=0.0
    if updated:
        if updated.tzinfo is None: updated=updated.replace(tzinfo=timezone.utc)
        age=max((datetime.now(timezone.utc)-updated).total_seconds(),0)/31557600.0
    freshness=max(0.35,1/(1+age))
    usage=min(1.20,1+log(1+float(row.get("access_count") or 0))*0.05)
    temporal=0.45 if row.get("valid_to") else 1.0
    return round(min(1.5,max(0.0,importance*confidence*trust*freshness*usage*temporal)),4)


def _queue_enrichment(memory_id: str, actor: str):
    try:
        from app.knowledge import queue_memory_enrichment
        queue_memory_enrichment(memory_id, actor)
    except Exception:
        pass


def memory_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {key:value for key,value in row.items() if key != "embedding"}


def get(memory_id: str, include_deleted: bool=False, touch: bool=True):
    deleted_clause="" if include_deleted else "AND deleted_at IS NULL"
    with connect() as conn:
        row=conn.execute(f"SELECT {MEMORY_FIELDS}, deleted_at, deleted_by FROM memories WHERE id=%s {deleted_clause}",(memory_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Memory not found")
        if touch and not include_deleted:
            conn.execute("UPDATE memories SET access_count=access_count+1,last_accessed_at=now() WHERE id=%s",(memory_id,)); conn.commit()
        newer=conn.execute("SELECT id,title,valid_from,valid_to FROM memories WHERE supersedes_memory_id=%s AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1",(memory_id,)).fetchone()
        older=conn.execute("SELECT id,title,valid_from,valid_to FROM memories WHERE id=%s",(row["supersedes_memory_id"],)).fetchone() if row["supersedes_memory_id"] else None
    item=dict(row); item["memory_score"]=_score(item); item["superseded_by"]=dict(newer) if newer else None; item["supersedes"]=dict(older) if older else None; item["temporal_state"]="historical" if item.get("valid_to") else "current"
    return item


def list_memories(limit=50,offset=0,memory_type=None,tag=None,include_deleted=False,include_historical=False):
    clauses=[]; params=[]
    if not include_deleted: clauses.append("deleted_at IS NULL")
    if not include_historical: clauses.append("(valid_to IS NULL OR valid_to > now())")
    if memory_type: clauses.append("memory_type=%s"); params.append(memory_type)
    if tag: clauses.append("%s=ANY(tags)"); params.append(tag)
    where="WHERE "+" AND ".join(clauses) if clauses else ""
    params.extend([limit,offset])
    with connect() as conn:
        rows=conn.execute(f"SELECT {MEMORY_FIELDS}, deleted_at, deleted_by, {MEMORY_SCORE_SQL} AS memory_score FROM memories {where} ORDER BY memory_score DESC,updated_at DESC LIMIT %s OFFSET %s",params).fetchall()
    out=[]
    for row in rows:
        item=dict(row); item["memory_score"]=float(item["memory_score"] or 0); out.append(item)
    return out


def _save_version(conn,memory_id: str,snapshot: dict,actor: str,reason: str|None):
    version=conn.execute("SELECT coalesce(max(version_no),0)+1 AS next FROM memory_versions WHERE memory_id=%s",(memory_id,)).fetchone()["next"]
    conn.execute("INSERT INTO memory_versions(memory_id,version_no,snapshot,actor,reason) VALUES (%s,%s,%s::jsonb,%s,%s)",(memory_id,version,json_text(snapshot),actor,reason))


def create(payload: dict[str,Any],actor: str,owner_id: str|None):
    tags=sorted({tag.strip().lower() for tag in payload.get("tags",[]) if tag.strip()})
    vector=embed_literal(f"{payload['title']}\n{payload['content']}")
    trust=payload.get("source_trust")
    if trust is None: trust=_default_source_trust(payload.get("source_type","manual"))
    with connect() as conn:
        row=conn.execute(f"""
          INSERT INTO memories(owner_id,title,content,memory_type,importance,confidence,tags,source_type,source_ref,metadata,created_by,updated_by,embedding,valid_from,valid_to,supersedes_memory_id,source_trust)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::vector,%s,%s,%s,%s) RETURNING {MEMORY_FIELDS}
        """,(owner_id,payload["title"],payload["content"],payload.get("memory_type","general"),payload.get("importance",5),payload.get("confidence",1.0),tags,payload.get("source_type","manual"),payload.get("source_ref"),json_text(payload.get("metadata",{})),actor,actor,vector,payload.get("valid_from"),payload.get("valid_to"),payload.get("supersedes_memory_id"),trust)).fetchone(); conn.commit()
    result=dict(row); result["memory_score"]=_score(result); _queue_enrichment(str(row["id"]),actor); return result


def update(memory_id: str,changes: dict[str,Any],actor: str):
    old=get(memory_id,touch=False); merged=dict(old); reason=changes.pop("reason",None)
    for key,value in changes.items():
        if value is not None: merged[key]=value
    if "tags" in changes and changes["tags"] is not None: merged["tags"]=sorted({tag.strip().lower() for tag in changes["tags"] if tag.strip()})
    vector=embed_literal(f"{merged['title']}\n{merged['content']}")
    with connect() as conn:
        _save_version(conn,memory_id,memory_snapshot(old),actor,reason)
        row=conn.execute(f"""
          UPDATE memories SET title=%s,content=%s,memory_type=%s,importance=%s,confidence=%s,tags=%s,source_type=%s,source_ref=%s,metadata=%s::jsonb,updated_by=%s,embedding=%s::vector,valid_from=%s,valid_to=%s,source_trust=%s,updated_at=now()
          WHERE id=%s AND deleted_at IS NULL RETURNING {MEMORY_FIELDS}
        """,(merged["title"],merged["content"],merged["memory_type"],merged["importance"],merged["confidence"],merged["tags"],merged["source_type"],merged.get("source_ref"),json_text(merged.get("metadata",{})),actor,vector,merged.get("valid_from"),merged.get("valid_to"),merged.get("source_trust",_default_source_trust(merged.get("source_type"))),memory_id)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Memory not found")
        conn.commit()
    result=dict(row); result["memory_score"]=_score(result); _queue_enrichment(memory_id,actor); return result,old,reason


def supersede(memory_id: str,payload: dict[str,Any],actor: str,owner_id: str|None):
    old=get(memory_id,touch=False); vector=embed_literal(f"{payload['title']}\n{payload['content']}"); tags=sorted({tag.strip().lower() for tag in payload.get("tags",[]) if tag.strip()}) or old["tags"]
    trust=payload.get("source_trust") if payload.get("source_trust") is not None else _default_source_trust(payload.get("source_type",old["source_type"]))
    with connect() as conn:
        valid_from=payload.get("valid_from") or conn.execute("SELECT now() AS n").fetchone()["n"]
        _save_version(conn,memory_id,memory_snapshot(old),actor,payload.get("reason") or "Superseded by newer information")
        conn.execute("UPDATE memories SET valid_to=%s,updated_by=%s,updated_at=now() WHERE id=%s",(valid_from,actor,memory_id))
        row=conn.execute(f"""
          INSERT INTO memories(owner_id,title,content,memory_type,importance,confidence,tags,source_type,source_ref,metadata,created_by,updated_by,embedding,valid_from,valid_to,supersedes_memory_id,source_trust)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::vector,%s,%s,%s,%s) RETURNING {MEMORY_FIELDS}
        """,(owner_id or old.get("owner_id"),payload["title"],payload["content"],payload.get("memory_type") or old["memory_type"],payload.get("importance") or old["importance"],payload.get("confidence") if payload.get("confidence") is not None else old["confidence"],tags,payload.get("source_type") or old["source_type"],payload.get("source_ref") or old.get("source_ref"),json_text(payload.get("metadata") or old.get("metadata",{})),actor,actor,vector,valid_from,payload.get("valid_to"),memory_id,trust)).fetchone(); conn.commit()
    _queue_enrichment(str(row["id"]),actor); return dict(row),old


def search(query: str,limit: int,memory_type: str|None,include_historical: bool=False):
    qvec=embed_literal(query); history="" if include_historical else "AND (valid_to IS NULL OR valid_to > now())"
    with connect() as conn:
        rows=conn.execute(f"""
          SELECT {MEMORY_FIELDS},1-(embedding<=>%s::vector) AS semantic_score,ts_rank_cd(search_vector,websearch_to_tsquery('english',%s)) AS lexical_score,{MEMORY_SCORE_SQL} AS memory_score
          FROM memories WHERE deleted_at IS NULL AND embedding IS NOT NULL {history} AND (%s::text IS NULL OR memory_type=%s)
          ORDER BY ((1-(embedding<=>%s::vector))*.72 + LEAST(ts_rank_cd(search_vector,websearch_to_tsquery('english',%s)),1.0)*.13 + ({MEMORY_SCORE_SQL})*.15) DESC LIMIT %s
        """,(qvec,query,memory_type,memory_type,qvec,query,limit)).fetchall()
        ids=[r["id"] for r in rows]
        if ids: conn.execute("UPDATE memories SET access_count=access_count+1,last_accessed_at=now() WHERE id=ANY(%s::uuid[])",(ids,)); conn.commit()
    out=[]
    for row in rows:
        item=dict(row); item["semantic_score"]=float(item["semantic_score"] or 0); item["lexical_score"]=float(item["lexical_score"] or 0); item["memory_score"]=float(item["memory_score"] or 0); item["result_type"]="memory"; out.append(item)
    return out
def request_delete(memory_id: str, actor: str, reason: str):
    memory = get(memory_id)
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM deletion_requests WHERE memory_id=%s AND status='pending'",
            (memory_id,),
        ).fetchone()
        if existing:
            return dict(existing), memory
        row = conn.execute(
            """
            INSERT INTO deletion_requests(memory_id, requested_by, reason)
            VALUES (%s,%s,%s)
            RETURNING *
            """,
            (memory_id, actor, reason),
        ).fetchone()
        conn.commit()
    return dict(row), memory


def list_delete_requests():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT dr.*, m.title, m.memory_type
            FROM deletion_requests dr
            JOIN memories m ON m.id = dr.memory_id
            ORDER BY CASE dr.status WHEN 'pending' THEN 0 ELSE 1 END, dr.requested_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def approve_delete(request_id: str, actor: str):
    with connect() as conn:
        req = conn.execute(
            "SELECT * FROM deletion_requests WHERE id=%s FOR UPDATE",
            (request_id,),
        ).fetchone()
        if not req:
            raise HTTPException(status_code=404, detail="Deletion request not found")
        if req["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"Request already {req['status']}")

        old = conn.execute(
            f"SELECT {MEMORY_FIELDS}, deleted_at, deleted_by FROM memories WHERE id=%s AND deleted_at IS NULL",
            (req["memory_id"],),
        ).fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Memory already deleted")

        _save_version(conn, str(req["memory_id"]), memory_snapshot(dict(old)), actor, req["reason"])
        conn.execute(
            "UPDATE memories SET deleted_at=now(), deleted_by=%s, updated_by=%s, updated_at=now() WHERE id=%s",
            (actor, actor, req["memory_id"]),
        )
        conn.execute(
            """
            UPDATE deletion_requests
            SET status='approved', reviewed_by=%s, reviewed_at=now()
            WHERE id=%s
            """,
            (actor, request_id),
        )
        conn.commit()
    return {"status": "approved", "memory_id": str(req["memory_id"])}, dict(old), req["reason"]


def reject_delete(request_id: str, actor: str, reason: str):
    with connect() as conn:
        row = conn.execute(
            """
            UPDATE deletion_requests
            SET status='rejected', reviewed_by=%s, reviewed_at=now()
            WHERE id=%s AND status='pending'
            RETURNING *
            """,
            (actor, request_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pending deletion request not found")
        conn.commit()
    return dict(row)


def restore(memory_id: str, actor: str):
    old = get(memory_id, include_deleted=True)
    if not old.get("deleted_at"):
        raise HTTPException(status_code=409, detail="Memory is not deleted")
    with connect() as conn:
        conn.execute(
            """
            UPDATE memories
            SET deleted_at=NULL, deleted_by=NULL, updated_by=%s, updated_at=now()
            WHERE id=%s
            """,
            (actor, memory_id),
        )
        conn.commit()
    return get(memory_id), old


def versions(memory_id: str):
    get(memory_id, include_deleted=True)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT version_no, snapshot, actor, reason, created_at
            FROM memory_versions
            WHERE memory_id=%s
            ORDER BY version_no DESC
            """,
            (memory_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_relation(from_id: str, to_id: str, relation_type: str, actor: str):
    get(from_id)
    get(to_id)
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO memory_relations(from_memory_id, to_memory_id, relation_type, created_by)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (from_memory_id, to_memory_id, relation_type)
            DO UPDATE SET relation_type=EXCLUDED.relation_type
            RETURNING *
            """,
            (from_id, to_id, relation_type.strip().lower(), actor),
        ).fetchone()
        conn.commit()
    return dict(row)


def relations(memory_id: str):
    get(memory_id)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.relation_type, r.from_memory_id, r.to_memory_id,
                   a.title AS from_title, b.title AS to_title, r.created_at
            FROM memory_relations r
            JOIN memories a ON a.id=r.from_memory_id
            JOIN memories b ON b.id=r.to_memory_id
            WHERE r.from_memory_id=%s OR r.to_memory_id=%s
            ORDER BY r.created_at DESC
            """,
            (memory_id, memory_id),
        ).fetchall()
    return [dict(row) for row in rows]
