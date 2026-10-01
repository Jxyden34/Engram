import re
from typing import Any

from fastapi import HTTPException
from redis import Redis
from rq import Queue

from app.config import settings
from app.database import connect, current_project_id, project_job
from app.embeddings import embed
from app.memories import create as create_memory
from app.util import vector_literal
from app.chatgpt_import import (
    DURABLE_MEMORY_SYSTEM,
    _compare,
    _nearest_memory,
    _normalise_candidate,
    _ollama_json,
)


def queue():
    return Queue("document-ingest", connection=Redis.from_url(settings().redis_url))


def list_ready_documents():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.filename, d.content_type, d.byte_size,
                   d.created_at, d.processed_at,
                   (
                       SELECT j.status
                       FROM document_memory_jobs j
                       WHERE j.document_id=d.id
                       ORDER BY j.created_at DESC
                       LIMIT 1
                   ) AS latest_analysis_status,
                   (
                       SELECT count(*)
                       FROM document_candidate_memories c
                       WHERE c.document_id=d.id AND c.status='pending'
                   ) AS pending_candidates
            FROM documents d
            WHERE d.deleted_at IS NULL
              AND d.status='ready'
              AND NOT (lower(d.filename) LIKE '%%conversation%%.json')
            ORDER BY d.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def create_job(document_id: str, actor: str, owner_id: str | None):
    with connect() as conn:
        document = conn.execute(
            """
            SELECT id, filename, status
            FROM documents
            WHERE id=%s AND deleted_at IS NULL
            """,
            (document_id,),
        ).fetchone()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        if document["status"] != "ready":
            raise HTTPException(status_code=409, detail=f"Document is {document['status']}")

        running = conn.execute(
            """
            SELECT *
            FROM document_memory_jobs
            WHERE document_id=%s AND status IN ('queued','processing')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        if running:
            return dict(running)

        pending = conn.execute(
            """
            SELECT count(*) AS n
            FROM document_candidate_memories
            WHERE document_id=%s AND status='pending'
            """,
            (document_id,),
        ).fetchone()["n"]
        if pending:
            raise HTTPException(
                status_code=409,
                detail="This document already has pending candidate memories. Review them before re-analysing.",
            )

        chunk_count = conn.execute(
            "SELECT count(*) AS n FROM document_chunks WHERE document_id=%s",
            (document_id,),
        ).fetchone()["n"]
        if not chunk_count:
            raise HTTPException(status_code=409, detail="Document has no extracted text chunks")

        row = conn.execute(
            """
            INSERT INTO document_memory_jobs(
                document_id, owner_id, requested_by, model_name, chunk_count
            )
            VALUES (%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (document_id, owner_id, actor, settings().chat_model, chunk_count),
        ).fetchone()
        conn.commit()

    queue().enqueue(
        "app.document_memory_import.process_document_job",
        str(row["id"]),
        job_timeout="6h",
        meta={"project_id": current_project_id()},
    )
    return dict(row)


def create_jobs_for_all_ready(actor: str, owner_id: str | None):
    docs = list_ready_documents()
    queued, skipped, errors = [], [], []

    for doc in docs:
        if int(doc.get("pending_candidates") or 0) > 0:
            skipped.append({
                "document_id": str(doc["id"]),
                "filename": doc["filename"],
                "reason": "pending candidates already exist",
            })
            continue
        try:
            job = create_job(str(doc["id"]), actor, owner_id)
            queued.append({
                "job_id": str(job["id"]),
                "document_id": str(doc["id"]),
                "filename": doc["filename"],
            })
        except Exception as exc:
            errors.append({
                "document_id": str(doc["id"]),
                "filename": doc["filename"],
                "error": str(exc),
            })

    return {
        "queued": len(queued),
        "skipped": len(skipped),
        "errors": len(errors),
        "jobs": queued,
        "skipped_items": skipped,
        "error_items": errors,
    }


def _group_chunks(rows: list[dict[str, Any]], max_chars: int):
    groups, current, size = [], [], 0
    for row in rows:
        if current and size + len(row["content"]) > max_chars:
            groups.append(current)
            current, size = [], 0
        current.append(row)
        size += len(row["content"])
    if current:
        groups.append(current)
    return groups


def _prompt(filename: str, rows: list[dict[str, Any]]) -> str:
    body = "\n\n".join(
        f"[Chunk {row['chunk_index']}]\n{row['content']}" for row in rows
    )
    return (
        f"Source document: {filename}\n"
        f"Chunks: {rows[0]['chunk_index']}-{rows[-1]['chunk_index']}\n\n"
        f"{body}"
    )


@project_job
def process_document_job(job_id: str):
    with connect() as conn:
        job = conn.execute(
            """
            SELECT j.*, d.filename
            FROM document_memory_jobs j
            JOIN documents d ON d.id=j.document_id
            WHERE j.id=%s
            """,
            (job_id,),
        ).fetchone()

        if not job:
            return

        conn.execute(
            """
            UPDATE document_memory_jobs
            SET status='processing', started_at=now(), error_message=NULL
            WHERE id=%s
            """,
            (job_id,),
        )
        conn.commit()

    try:
        with connect() as conn:
            chunks = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT chunk_index, content
                    FROM document_chunks
                    WHERE document_id=%s
                    ORDER BY chunk_index
                    """,
                    (job["document_id"],),
                ).fetchall()
            ]

        if not chunks:
            raise RuntimeError("No document chunks were found")

        extracted = []
        processed = 0

        for group in _group_chunks(chunks, settings().chat_import_chunk_chars):
            result = _ollama_json(
                DURABLE_MEMORY_SYSTEM,
                (
                    f"Extract at most {settings().chat_import_max_candidates_per_chunk} "
                    f"durable memories from this document segment.\n\n"
                    f"{_prompt(job['filename'], group)}"
                ),
            )

            raw_items = result.get("memories") or []
            if not isinstance(raw_items, list):
                raw_items = []

            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                candidate = _normalise_candidate(raw)
                if not candidate:
                    continue
                candidate["_chunk_start"] = group[0]["chunk_index"]
                candidate["_chunk_end"] = group[-1]["chunk_index"]
                extracted.append(candidate)

            processed += len(group)
            with connect() as conn:
                conn.execute(
                    "UPDATE document_memory_jobs SET processed_chunks=%s WHERE id=%s",
                    (processed, job_id),
                )
                conn.commit()

        unique, seen = [], set()
        for candidate in extracted:
            key = re.sub(r"\W+", " ", candidate["content"].lower()).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(candidate)

        for candidate in unique:
            emb = embed(f"{candidate['title']}\n{candidate['content']}")
            nearest = _nearest_memory(emb)
            comparison, reason = _compare(candidate, nearest)

            excerpt = candidate.get("source_excerpt") or ""
            if reason:
                excerpt = (excerpt + f"\nComparison hint: {reason}").strip()

            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO document_candidate_memories(
                        job_id, document_id, owner_id,
                        title, content, memory_type, importance, confidence, tags,
                        source_excerpt, source_chunk_start, source_chunk_end,
                        embedding, nearest_memory_id, nearest_similarity, comparison
                    )
                    VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s::vector,%s,%s,%s
                    )
                    """,
                    (
                        job_id,
                        job["document_id"],
                        job["owner_id"],
                        candidate["title"],
                        candidate["content"],
                        candidate["memory_type"],
                        candidate["importance"],
                        candidate["confidence"],
                        candidate["tags"],
                        excerpt[:2400] or None,
                        candidate["_chunk_start"],
                        candidate["_chunk_end"],
                        vector_literal(emb),
                        nearest["id"] if nearest else None,
                        nearest["similarity"] if nearest else None,
                        comparison,
                    ),
                )
                conn.commit()

        with connect() as conn:
            count = conn.execute(
                "SELECT count(*) AS n FROM document_candidate_memories WHERE job_id=%s",
                (job_id,),
            ).fetchone()["n"]
            conn.execute(
                """
                UPDATE document_memory_jobs
                SET status='ready',
                    processed_chunks=chunk_count,
                    candidate_count=%s,
                    completed_at=now()
                WHERE id=%s
                """,
                (count, job_id),
            )
            conn.commit()

    except Exception as exc:
        with connect() as conn:
            conn.execute(
                """
                UPDATE document_memory_jobs
                SET status='failed', error_message=%s, completed_at=now()
                WHERE id=%s
                """,
                (str(exc)[:4000], job_id),
            )
            conn.commit()
        raise


def list_jobs():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT j.id, j.document_id, d.filename, j.status, j.model_name,
                   j.chunk_count, j.processed_chunks, j.candidate_count,
                   j.error_message, j.created_at, j.started_at, j.completed_at
            FROM document_memory_jobs j
            JOIN documents d ON d.id=j.document_id
            ORDER BY j.created_at DESC
            LIMIT 250
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_candidates(status="pending", comparison=None, limit=300, offset=0):
    clauses = ["c.status=%s"]
    params: list[Any] = [status]

    if comparison:
        clauses.append("c.comparison=%s")
        params.append(comparison)

    params.extend([limit, offset])

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.job_id, c.document_id, c.title, c.content,
                   c.memory_type, c.importance, c.confidence, c.tags,
                   c.source_excerpt, c.source_chunk_start, c.source_chunk_end,
                   c.nearest_memory_id, c.nearest_similarity, c.comparison,
                   c.status, c.created_at,
                   d.filename AS source_filename,
                   m.title AS nearest_memory_title,
                   m.content AS nearest_memory_content
            FROM document_candidate_memories c
            JOIN documents d ON d.id=c.document_id
            LEFT JOIN memories m ON m.id=c.nearest_memory_id
            WHERE {' AND '.join(clauses)}
            ORDER BY
                CASE c.comparison
                    WHEN 'conflicts' THEN 0
                    WHEN 'updates' THEN 1
                    WHEN 'duplicate' THEN 2
                    WHEN 'related' THEN 3
                    ELSE 4
                END,
                c.confidence DESC,
                c.created_at ASC
            LIMIT %s OFFSET %s
            """,
            params,
        ).fetchall()

    out = []
    for row in rows:
        item = dict(row)
        item["confidence"] = float(item["confidence"])
        if item.get("nearest_similarity") is not None:
            item["nearest_similarity"] = float(item["nearest_similarity"])
        out.append(item)
    return out


def update_candidate(candidate_id: str, changes: dict[str, Any]):
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM document_candidate_memories WHERE id=%s",
            (candidate_id,),
        ).fetchone()

    if not existing:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if existing["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Candidate already {existing['status']}")

    merged = dict(existing)
    for key in ("title", "content", "memory_type", "importance", "confidence", "tags"):
        if key in changes and changes[key] is not None:
            merged[key] = changes[key]

    emb = embed(f"{merged['title']}\n{merged['content']}")
    nearest = _nearest_memory(emb)
    comparison, reason = _compare(merged, nearest)

    excerpt = existing["source_excerpt"] or ""
    if reason:
        excerpt = excerpt.split("\nComparison hint:")[0].strip()
        excerpt = (excerpt + f"\nComparison hint: {reason}").strip()

    with connect() as conn:
        row = conn.execute(
            """
            UPDATE document_candidate_memories
            SET title=%s, content=%s, memory_type=%s, importance=%s,
                confidence=%s, tags=%s, source_excerpt=%s,
                embedding=%s::vector, nearest_memory_id=%s,
                nearest_similarity=%s, comparison=%s, updated_at=now()
            WHERE id=%s
            RETURNING *
            """,
            (
                str(merged["title"])[:300],
                str(merged["content"]),
                str(merged["memory_type"])[:80],
                max(1, min(10, int(merged["importance"]))),
                max(0.0, min(1.0, float(merged["confidence"]))),
                merged.get("tags") or [],
                excerpt[:2400] or None,
                vector_literal(emb),
                nearest["id"] if nearest else None,
                nearest["similarity"] if nearest else None,
                comparison,
                candidate_id,
            ),
        ).fetchone()
        conn.commit()

    return dict(row)


def accept_candidate(candidate_id: str, actor: str):
    with connect() as conn:
        candidate = conn.execute(
            """
            SELECT c.*, d.filename, d.content_type, d.source_type, d.source_ref,
                   d.source_metadata
            FROM document_candidate_memories c
            JOIN documents d ON d.id=c.document_id
            WHERE c.id=%s
            FOR UPDATE
            """,
            (candidate_id,),
        ).fetchone()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Candidate already {candidate['status']}")

    memory = create_memory(
        {
            "title": candidate["title"],
            "content": candidate["content"],
            "memory_type": candidate["memory_type"],
            "importance": candidate["importance"],
            "confidence": candidate["confidence"],
            "tags": candidate["tags"],
            "source_type": (
                "github_import" if candidate["source_type"] == "github"
                else "browser_capture" if candidate["source_type"] == "browser_capture"
                else "document_import"
            ),
            "source_ref": candidate["source_ref"] or f"document://{candidate['document_id']}",
            "metadata": {
                "document_candidate_id": str(candidate["id"]),
                "source_document_id": str(candidate["document_id"]),
                "source_filename": candidate["filename"],
                "source_content_type": candidate["content_type"],
                "source_chunk_start": candidate["source_chunk_start"],
                "source_chunk_end": candidate["source_chunk_end"],
                "source_excerpt": candidate["source_excerpt"],
                "original_source_type": candidate["source_type"],
                "original_source_ref": candidate["source_ref"],
                "original_source_metadata": candidate["source_metadata"],
            },
        },
        actor,
        str(candidate["owner_id"]) if candidate["owner_id"] else None,
    )

    with connect() as conn:
        conn.execute(
            """
            UPDATE document_candidate_memories
            SET status='accepted', reviewed_by=%s, reviewed_at=now(),
                accepted_memory_id=%s, updated_at=now()
            WHERE id=%s
            """,
            (actor, memory["id"], candidate_id),
        )
        conn.commit()

    return memory


def reject_candidate(candidate_id: str, actor: str):
    with connect() as conn:
        row = conn.execute(
            """
            UPDATE document_candidate_memories
            SET status='rejected', reviewed_by=%s,
                reviewed_at=now(), updated_at=now()
            WHERE id=%s AND status='pending'
            RETURNING id, status, reviewed_by, reviewed_at
            """,
            (actor, candidate_id),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Pending candidate not found")
        conn.commit()

    return dict(row)


def accept_safe(actor: str):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM document_candidate_memories
            WHERE status='pending'
              AND confidence >= 0.85
              AND (comparison='new' OR comparison IS NULL)
              AND (nearest_similarity IS NULL OR nearest_similarity < 0.78)
            ORDER BY created_at
            """
        ).fetchall()

    accepted, errors = [], []
    for row in rows:
        try:
            memory = accept_candidate(str(row["id"]), actor)
            accepted.append(str(memory["id"]))
        except Exception as exc:
            errors.append({"candidate_id": str(row["id"]), "error": str(exc)})

    return {"accepted": len(accepted), "memory_ids": accepted, "errors": errors}
