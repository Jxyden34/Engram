import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException
from redis import Redis
from rq import Queue

from app.config import settings
from app.database import connect, current_project_id, project_job
from app.documents import get_document, minio_client
from app.embeddings import embed, embed_literal
from app.memories import create as create_memory
from app.util import json_text, vector_literal


DURABLE_MEMORY_SYSTEM = """You extract durable personal memories from a conversation.

Return ONLY valid JSON with this shape:
{
  "memories": [
    {
      "title": "short descriptive title",
      "content": "one self-contained factual memory",
      "memory_type": "one concise category",
      "importance": 1,
      "confidence": 0.0,
      "tags": ["lowercase", "tags"],
      "source_excerpt": "brief supporting excerpt or paraphrase"
    }
  ]
}

Extract facts likely to remain useful in future conversations: stable preferences, projects,
devices, infrastructure, relationships, recurring responsibilities, qualifications, work
context, decisions, goals, important events and long-lived configuration facts.

Do NOT extract:
- greetings, jokes, thanks, filler, transient emotional reactions
- assistant guesses or claims not confirmed by the user
- passwords, API keys, secrets, tokens, recovery codes
- exact account numbers or other authentication material
- huge command/output dumps as memories
- duplicate restatements of the same fact

Prefer memories explicitly stated by the user. If a fact appears old or time-sensitive, make
the content time-aware rather than pretending it is timeless. Keep each memory atomic.
Importance is 1-10. Confidence is 0-1.
"""


COMPARISON_SYSTEM = """Compare a candidate personal memory with an existing memory.
Return ONLY JSON:
{
  "comparison": "new|duplicate|related|updates|conflicts",
  "reason": "brief reason"
}

duplicate = same underlying fact
related = same topic but compatible and distinct
updates = candidate is a newer/superseding version
conflicts = both cannot reasonably be true at the same time
new = unrelated enough to store separately
"""


def queue():
    return Queue("document-ingest", connection=Redis.from_url(settings().redis_url))


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        if isinstance(value, str):
            if value.replace(".", "", 1).isdigit():
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return None


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    parts = content.get("parts") or []

    output: list[str] = []
    for part in parts:
        if isinstance(part, str):
            output.append(part)
        elif isinstance(part, dict):
            # Export formats occasionally put text in nested objects.
            for key in ("text", "content", "caption"):
                value = part.get(key)
                if isinstance(value, str):
                    output.append(value)
                    break

    if not output:
        text = content.get("text")
        if isinstance(text, str):
            output.append(text)

    return "\n".join(value.strip() for value in output if value and value.strip()).strip()


def _active_mapping_nodes(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = conversation.get("mapping")
    if not isinstance(mapping, dict):
        return []

    current = conversation.get("current_node")
    if current and current in mapping:
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        node_id = current
        while node_id and node_id in mapping and node_id not in seen:
            seen.add(node_id)
            node = mapping[node_id]
            chain.append(node)
            node_id = node.get("parent")
        chain.reverse()
        return chain

    nodes = list(mapping.values())
    nodes.sort(
        key=lambda node: (
            ((node.get("message") or {}).get("create_time") is None),
            (node.get("message") or {}).get("create_time") or 0,
        )
    )
    return nodes


def conversation_messages(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for node in _active_mapping_nodes(conversation):
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        author = message.get("author") or {}
        role = author.get("role")
        if role not in {"user", "assistant"}:
            continue

        text = _message_text(message)
        if not text:
            continue

        output.append(
            {
                "role": role,
                "text": text,
                "create_time": _dt(message.get("create_time")),
            }
        )
    return output


def _conversation_text(title: str, messages: list[dict[str, Any]]) -> str:
    lines = [f"Conversation title: {title}", ""]
    for msg in messages:
        when = msg["create_time"].isoformat() if msg.get("create_time") else "unknown time"
        lines.append(f"[{when}] {msg['role'].upper()}:")
        lines.append(msg["text"])
        lines.append("")
    return "\n".join(lines).strip()


def _chunks(text: str, max_chars: int):
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = []
    size = 0
    blocks = re.split(r"\n(?=\[[^\]]+\] (?:USER|ASSISTANT):)", text)

    for block in blocks:
        if size + len(block) > max_chars and current:
            chunks.append("\n".join(current))
            current = []
            size = 0

        if len(block) > max_chars:
            start = 0
            while start < len(block):
                piece = block[start : start + max_chars]
                if current:
                    chunks.append("\n".join(current))
                    current = []
                    size = 0
                chunks.append(piece)
                start += max_chars
            continue

        current.append(block)
        size += len(block)

    if current:
        chunks.append("\n".join(current))
    return chunks


def _ollama_json(system: str, user: str) -> dict[str, Any]:
    cfg = settings()
    response = httpx.post(
        f"{cfg.ollama_url.rstrip('/')}/api/chat",
        json={
            "model": cfg.chat_model,
            "stream": False,
            "think": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0.15},
        },
        timeout=300.0,
    )
    response.raise_for_status()
    content = response.json()["message"]["content"].strip()
    return json.loads(content)


def _normalise_candidate(item: dict[str, Any]) -> dict[str, Any] | None:
    title = str(item.get("title") or "").strip()[:300]
    content = str(item.get("content") or "").strip()
    if not title or not content:
        return None

    memory_type = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(item.get("memory_type") or "general").strip().lower())
    memory_type = memory_type.strip("-")[:80] or "general"

    try:
        importance = max(1, min(10, int(item.get("importance", 5))))
    except Exception:
        importance = 5

    try:
        confidence = max(0.0, min(1.0, float(item.get("confidence", 0.8))))
    except Exception:
        confidence = 0.8

    tags_raw = item.get("tags") or []
    if not isinstance(tags_raw, list):
        tags_raw = []
    tags = sorted(
        {
            re.sub(r"\s+", "-", str(tag).strip().lower())[:80]
            for tag in tags_raw
            if str(tag).strip()
        }
    )[:30]

    excerpt = str(item.get("source_excerpt") or "").strip()[:1600] or None

    return {
        "title": title,
        "content": content,
        "memory_type": memory_type,
        "importance": importance,
        "confidence": confidence,
        "tags": tags,
        "source_excerpt": excerpt,
    }


def _nearest_memory(candidate_embedding: list[float]) -> dict[str, Any] | None:
    vec = vector_literal(candidate_embedding)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, title, content, memory_type,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM memories
            WHERE deleted_at IS NULL AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT 1
            """,
            (vec, vec),
        ).fetchone()

    if not row:
        return None

    result = dict(row)
    result["similarity"] = float(result["similarity"] or 0)
    return result


def _compare(candidate: dict[str, Any], nearest: dict[str, Any] | None) -> tuple[str, str | None]:
    if not nearest:
        return "new", None

    similarity = nearest["similarity"]
    if similarity >= 0.94:
        return "duplicate", "Very high semantic similarity to an existing memory."
    if similarity < 0.70:
        return "new", None

    try:
        data = _ollama_json(
            COMPARISON_SYSTEM,
            (
                "CANDIDATE:\n"
                f"Title: {candidate['title']}\n"
                f"Content: {candidate['content']}\n\n"
                "EXISTING:\n"
                f"Title: {nearest['title']}\n"
                f"Content: {nearest['content']}\n"
            ),
        )
        comparison = str(data.get("comparison") or "related").strip().lower()
        if comparison not in {"new", "duplicate", "related", "updates", "conflicts"}:
            comparison = "related"
        return comparison, str(data.get("reason") or "").strip()[:1000] or None
    except Exception:
        return "related", "Related by semantic similarity; comparison model could not classify it."


def _load_conversations(raw: bytes) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        raise ValueError("The selected document is not valid UTF-8 JSON") from exc

    if isinstance(data, list):
        conversations = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        for key in ("conversations", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                conversations = [item for item in value if isinstance(item, dict)]
                break
        else:
            conversations = [data] if "mapping" in data else []
    else:
        conversations = []

    if not conversations:
        raise ValueError("No ChatGPT conversations were found in this JSON file")
    return conversations


def create_import_job(source_document_id: str, actor: str, owner_id: str | None):
    document = get_document(source_document_id)
    if not document["filename"].lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="ChatGPT importer expects a JSON export file")

    with connect() as conn:
        existing = conn.execute(
            """
            SELECT *
            FROM chat_import_jobs
            WHERE source_document_id=%s AND status IN ('queued','processing')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_document_id,),
        ).fetchone()
        if existing:
            return dict(existing)

        row = conn.execute(
            """
            INSERT INTO chat_import_jobs(owner_id, source_document_id, requested_by, model_name)
            VALUES (%s,%s,%s,%s)
            RETURNING *
            """,
            (owner_id, source_document_id, actor, settings().chat_model),
        ).fetchone()
        conn.commit()

    queue().enqueue(
        "app.chatgpt_import.process_chatgpt_export",
        str(row["id"]),
        job_timeout="12h",
        meta={"project_id": current_project_id()},
    )
    return dict(row)


@project_job
def process_chatgpt_export(import_job_id: str):
    cfg = settings()

    with connect() as conn:
        job = conn.execute(
            """
            SELECT j.*, d.object_key, d.filename
            FROM chat_import_jobs j
            JOIN documents d ON d.id=j.source_document_id
            WHERE j.id=%s
            """,
            (import_job_id,),
        ).fetchone()
        if not job:
            return
        conn.execute(
            "UPDATE chat_import_jobs SET status='processing', started_at=now(), error_message=NULL WHERE id=%s",
            (import_job_id,),
        )
        conn.commit()

    response = None
    try:
        response = minio_client().get_object(cfg.minio_bucket, job["object_key"])
        raw = response.read()
        conversations = _load_conversations(raw)

        with connect() as conn:
            conn.execute(
                "UPDATE chat_import_jobs SET conversation_count=%s WHERE id=%s",
                (len(conversations), import_job_id),
            )
            conn.commit()

        for conversation in conversations:
            try:
                _process_conversation(dict(job), conversation)
                with connect() as conn:
                    conn.execute(
                        """
                        UPDATE chat_import_jobs
                        SET processed_conversations=processed_conversations+1
                        WHERE id=%s
                        """,
                        (import_job_id,),
                    )
                    conn.commit()
            except Exception as exc:
                with connect() as conn:
                    conn.execute(
                        """
                        UPDATE chat_import_jobs
                        SET processed_conversations=processed_conversations+1,
                            error_count=error_count+1
                        WHERE id=%s
                        """,
                        (import_job_id,),
                    )
                    conn.commit()

        with connect() as conn:
            candidate_count = conn.execute(
                "SELECT count(*) AS n FROM candidate_memories WHERE import_job_id=%s",
                (import_job_id,),
            ).fetchone()["n"]
            conn.execute(
                """
                UPDATE chat_import_jobs
                SET status='ready', candidate_count=%s, completed_at=now()
                WHERE id=%s
                """,
                (candidate_count, import_job_id),
            )
            conn.commit()

    except Exception as exc:
        with connect() as conn:
            conn.execute(
                """
                UPDATE chat_import_jobs
                SET status='failed', error_message=%s, completed_at=now()
                WHERE id=%s
                """,
                (str(exc)[:4000], import_job_id),
            )
            conn.commit()
        raise
    finally:
        if response is not None:
            response.close()
            response.release_conn()


def _process_conversation(job: dict[str, Any], conversation: dict[str, Any]):
    title = str(conversation.get("title") or "Untitled conversation").strip()[:500]
    external_id = str(conversation.get("conversation_id") or conversation.get("id") or "")[:500] or None
    create_time = _dt(conversation.get("create_time"))
    update_time = _dt(conversation.get("update_time"))

    messages = conversation_messages(conversation)
    if not messages:
        return

    full_text = _conversation_text(title, messages)
    source_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()

    with connect() as conn:
        existing = conn.execute(
            """
            SELECT id, status
            FROM chat_import_conversations
            WHERE import_job_id=%s AND source_hash=%s
            """,
            (job["id"], source_hash),
        ).fetchone()
        if existing and existing["status"] == "ready":
            return

        if existing:
            conv_id = str(existing["id"])
            conn.execute(
                """
                UPDATE chat_import_conversations
                SET status='processing', error_message=NULL
                WHERE id=%s
                """,
                (conv_id,),
            )
        else:
            row = conn.execute(
                """
                INSERT INTO chat_import_conversations(
                    import_job_id, external_conversation_id, title, create_time,
                    update_time, message_count, source_hash, status
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,'processing')
                RETURNING id
                """,
                (
                    job["id"],
                    external_id,
                    title,
                    create_time,
                    update_time,
                    len(messages),
                    source_hash,
                ),
            ).fetchone()
            conv_id = str(row["id"])
        conn.commit()

    try:
        all_candidates: list[dict[str, Any]] = []
        for index, chunk in enumerate(_chunks(full_text, settings().chat_import_chunk_chars)):
            result = _ollama_json(
                DURABLE_MEMORY_SYSTEM,
                (
                    f"Extract at most {settings().chat_import_max_candidates_per_chunk} durable memories "
                    f"from this conversation segment ({index + 1}).\n\n{chunk}"
                ),
            )
            memories = result.get("memories") or []
            if not isinstance(memories, list):
                continue
            for item in memories:
                if isinstance(item, dict):
                    normalised = _normalise_candidate(item)
                    if normalised:
                        all_candidates.append(normalised)

        # De-dupe candidates within the same conversation by normalized content.
        unique = []
        seen = set()
        for candidate in all_candidates:
            key = re.sub(r"\W+", " ", candidate["content"].lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)

        first_time = next((m["create_time"] for m in messages if m.get("create_time")), create_time)
        last_time = next((m["create_time"] for m in reversed(messages) if m.get("create_time")), update_time)

        with connect() as conn:
            # Reprocessing a failed conversation should not duplicate candidates.
            conn.execute("DELETE FROM candidate_memories WHERE import_conversation_id=%s AND status='pending'", (conv_id,))
            conn.commit()

        for candidate in unique:
            candidate_embedding = embed(f"{candidate['title']}\n{candidate['content']}")
            nearest = _nearest_memory(candidate_embedding)
            comparison, comparison_reason = _compare(candidate, nearest)

            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO candidate_memories(
                        import_job_id, import_conversation_id, owner_id,
                        title, content, memory_type, importance, confidence, tags,
                        source_excerpt, source_message_start, source_message_end,
                        embedding, nearest_memory_id, nearest_similarity, comparison
                    )
                    VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s::vector,%s,%s,%s
                    )
                    """,
                    (
                        job["id"],
                        conv_id,
                        job["owner_id"],
                        candidate["title"],
                        candidate["content"],
                        candidate["memory_type"],
                        candidate["importance"],
                        candidate["confidence"],
                        candidate["tags"],
                        (
                            (candidate["source_excerpt"] or "")
                            + (f"\nComparison hint: {comparison_reason}" if comparison_reason else "")
                        )[:2400] or None,
                        first_time,
                        last_time,
                        vector_literal(candidate_embedding),
                        nearest["id"] if nearest else None,
                        nearest["similarity"] if nearest else None,
                        comparison,
                    ),
                )
                conn.commit()

        with connect() as conn:
            conn.execute(
                "UPDATE chat_import_conversations SET status='ready' WHERE id=%s",
                (conv_id,),
            )
            conn.commit()

    except Exception as exc:
        with connect() as conn:
            conn.execute(
                """
                UPDATE chat_import_conversations
                SET status='failed', error_message=%s
                WHERE id=%s
                """,
                (str(exc)[:4000], conv_id),
            )
            conn.commit()
        raise


def list_eligible_documents():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.filename, d.byte_size, d.created_at, d.status,
                   (
                       SELECT j.status
                       FROM chat_import_jobs j
                       WHERE j.source_document_id=d.id
                       ORDER BY j.created_at DESC
                       LIMIT 1
                   ) AS latest_import_status
            FROM documents d
            WHERE d.deleted_at IS NULL
              AND lower(d.filename) LIKE '%%conversation%%.json'
            ORDER BY d.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_jobs():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT j.id, j.source_document_id, d.filename, j.status, j.model_name,
                   j.conversation_count, j.processed_conversations, j.candidate_count,
                   j.error_count, j.error_message, j.created_at, j.started_at, j.completed_at
            FROM chat_import_jobs j
            JOIN documents d ON d.id=j.source_document_id
            ORDER BY j.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def candidate_stats():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT status, coalesce(comparison, 'new') AS comparison, count(*) AS count
            FROM candidate_memories
            GROUP BY status, coalesce(comparison, 'new')
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_candidates(
    status: str = "pending",
    comparison: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    clauses = ["c.status=%s"]
    params: list[Any] = [status]
    if comparison:
        clauses.append("c.comparison=%s")
        params.append(comparison)
    params.extend([limit, offset])

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.import_job_id, c.title, c.content, c.memory_type,
                   c.importance, c.confidence, c.tags, c.source_excerpt,
                   c.source_message_start, c.source_message_end,
                   c.nearest_memory_id, c.nearest_similarity, c.comparison,
                   c.status, c.created_at,
                   ic.title AS conversation_title,
                   ic.external_conversation_id,
                   j.source_document_id,
                   d.filename AS source_filename,
                   m.title AS nearest_memory_title,
                   m.content AS nearest_memory_content
            FROM candidate_memories c
            JOIN chat_import_conversations ic ON ic.id=c.import_conversation_id
            JOIN chat_import_jobs j ON j.id=c.import_job_id
            JOIN documents d ON d.id=j.source_document_id
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

    result = []
    for row in rows:
        item = dict(row)
        if item.get("confidence") is not None:
            item["confidence"] = float(item["confidence"])
        if item.get("nearest_similarity") is not None:
            item["nearest_similarity"] = float(item["nearest_similarity"])
        result.append(item)
    return result


def update_candidate(candidate_id: str, changes: dict[str, Any]):
    allowed = {"title", "content", "memory_type", "importance", "confidence", "tags"}
    values = {k: v for k, v in changes.items() if k in allowed and v is not None}
    if not values:
        return get_candidate(candidate_id)

    existing = get_candidate(candidate_id)
    merged = dict(existing)
    merged.update(values)
    candidate_embedding = embed(f"{merged['title']}\n{merged['content']}")
    nearest = _nearest_memory(candidate_embedding)
    comparison, comparison_reason = _compare(merged, nearest)

    with connect() as conn:
        row = conn.execute(
            """
            UPDATE candidate_memories
            SET title=%s, content=%s, memory_type=%s, importance=%s, confidence=%s,
                tags=%s, embedding=%s::vector, nearest_memory_id=%s,
                nearest_similarity=%s, comparison=%s, updated_at=now()
            WHERE id=%s AND status='pending'
            RETURNING *
            """,
            (
                str(merged["title"])[:300],
                str(merged["content"]),
                str(merged["memory_type"])[:80],
                max(1, min(10, int(merged["importance"]))),
                max(0.0, min(1.0, float(merged["confidence"]))),
                merged.get("tags") or [],
                vector_literal(candidate_embedding),
                nearest["id"] if nearest else None,
                nearest["similarity"] if nearest else None,
                comparison,
                candidate_id,
            ),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pending candidate not found")
        conn.commit()
    return dict(row)


def get_candidate(candidate_id: str):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM candidate_memories WHERE id=%s",
            (candidate_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate memory not found")
    return dict(row)


def accept_candidate(candidate_id: str, actor: str):
    with connect() as conn:
        candidate = conn.execute(
            """
            SELECT c.*, ic.title AS conversation_title, ic.external_conversation_id,
                   j.source_document_id, d.filename AS source_filename
            FROM candidate_memories c
            JOIN chat_import_conversations ic ON ic.id=c.import_conversation_id
            JOIN chat_import_jobs j ON j.id=c.import_job_id
            JOIN documents d ON d.id=j.source_document_id
            WHERE c.id=%s
            FOR UPDATE
            """,
            (candidate_id,),
        ).fetchone()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        if candidate["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"Candidate already {candidate['status']}")

    source_ref = (
        f"chatgpt://conversation/{candidate['external_conversation_id']}"
        if candidate["external_conversation_id"]
        else f"chatgpt://import/{candidate['import_conversation_id']}"
    )

    memory = create_memory(
        {
            "title": candidate["title"],
            "content": candidate["content"],
            "memory_type": candidate["memory_type"],
            "importance": candidate["importance"],
            "confidence": candidate["confidence"],
            "tags": candidate["tags"],
            "source_type": "chatgpt_import",
            "source_ref": source_ref,
            "metadata": {
                "candidate_memory_id": str(candidate["id"]),
                "source_document_id": str(candidate["source_document_id"]),
                "source_filename": candidate["source_filename"],
                "conversation_title": candidate["conversation_title"],
                "external_conversation_id": candidate["external_conversation_id"],
                "source_message_start": (
                    candidate["source_message_start"].isoformat()
                    if candidate["source_message_start"]
                    else None
                ),
                "source_message_end": (
                    candidate["source_message_end"].isoformat()
                    if candidate["source_message_end"]
                    else None
                ),
                "source_excerpt": candidate["source_excerpt"],
            },
        },
        actor,
        str(candidate["owner_id"]) if candidate["owner_id"] else None,
    )

    with connect() as conn:
        conn.execute(
            """
            UPDATE candidate_memories
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
            UPDATE candidate_memories
            SET status='rejected', reviewed_by=%s, reviewed_at=now(), updated_at=now()
            WHERE id=%s AND status='pending'
            RETURNING id, status, reviewed_by, reviewed_at
            """,
            (actor, candidate_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pending candidate not found")
        conn.commit()
    return dict(row)


def accept_safe_candidates(actor: str, job_id: str | None = None):
    clauses = [
        "status='pending'",
        "confidence >= 0.85",
        "(comparison='new' OR comparison IS NULL)",
        "(nearest_similarity IS NULL OR nearest_similarity < 0.78)",
    ]
    params: list[Any] = []
    if job_id:
        clauses.append("import_job_id=%s")
        params.append(job_id)

    with connect() as conn:
        rows = conn.execute(
            f"SELECT id FROM candidate_memories WHERE {' AND '.join(clauses)} ORDER BY created_at",
            params,
        ).fetchall()

    accepted = []
    errors = []
    for row in rows:
        try:
            memory = accept_candidate(str(row["id"]), actor)
            accepted.append(str(memory["id"]))
        except Exception as exc:
            errors.append({"candidate_id": str(row["id"]), "error": str(exc)})
    return {"accepted": len(accepted), "memory_ids": accepted, "errors": errors}
