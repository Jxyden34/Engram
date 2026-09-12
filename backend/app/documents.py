import hashlib
import io
import json
import mimetypes
import stat
import zipfile
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from minio import Minio
from redis import Redis
from rq import Queue

from app.config import settings
from app.database import connect
from app.embeddings import embed_literal


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".log",
    ".yaml",
    ".yml",
    ".py",
    ".ps1",
    ".sh",
    ".bash",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".cs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".sql",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
    ".html",
    ".css",
}

IGNORED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}


def minio_client():
    cfg = settings()
    return Minio(
        cfg.minio_endpoint,
        access_key=cfg.minio_access_key,
        secret_key=cfg.minio_secret_key,
        secure=cfg.minio_secure,
    )


def enqueue():
    return Queue("document-ingest", connection=Redis.from_url(settings().redis_url))


def safe_relative_name(value: str | None) -> str:
    raw = (value or "upload.bin").replace("\\", "/").replace("\x00", "").strip()
    while raw.startswith("./"):
        raw = raw[2:]

    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Unsafe file path")

    clean_parts = []
    for part in path.parts:
        clean = "".join(ch for ch in part if ch.isprintable() and ch not in {":", "\r", "\n"}).strip()
        if not clean:
            clean = "_"
        clean_parts.append(clean[:240])

    return "/".join(clean_parts)[:1400]


def is_ignored(name: str) -> bool:
    path = PurePosixPath(name)
    if path.name in IGNORED_NAMES:
        return True
    if "__MACOSX" in path.parts:
        return True
    return any(part.startswith(".") and part not in {".well-known"} for part in path.parts[:-1])


def is_supported(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in SUPPORTED_EXTENSIONS


def _find_duplicate(digest: str):
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, filename, content_type, byte_size, sha256, status,
                   extraction_error, uploaded_by, source_type, source_ref, source_metadata,
                   created_at, processed_at
            FROM documents
            WHERE sha256=%s AND deleted_at IS NULL
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (digest,),
        ).fetchone()
    return dict(row) if row else None


def store_bytes(
    raw: bytes,
    filename: str,
    content_type: str | None,
    actor: str,
    owner_id: str | None,
    source_type: str = "upload",
    source_ref: str | None = None,
    source_metadata: dict | None = None,
    dedupe: bool = True,
):
    cfg = settings()
    max_bytes = cfg.max_upload_mb * 1024 * 1024

    if not raw:
        raise HTTPException(status_code=400, detail=f"Empty file: {filename}")
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{filename} exceeds the per-document limit of {cfg.max_upload_mb} MB",
        )

    try:
        safe_name = safe_relative_name(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unsafe filename: {filename}") from exc

    if not is_supported(safe_name):
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {safe_name}")

    digest = hashlib.sha256(raw).hexdigest()
    if dedupe:
        duplicate = _find_duplicate(digest)
        if duplicate:
            duplicate["duplicate"] = True
            duplicate["submitted_filename"] = safe_name
            return duplicate

    document_id = str(uuid4())
    object_key = f"{document_id}/{safe_name}"
    guessed_type = mimetypes.guess_type(safe_name)[0]
    stored_type = content_type or guessed_type or "application/octet-stream"

    minio_client().put_object(
        cfg.minio_bucket,
        object_key,
        io.BytesIO(raw),
        length=len(raw),
        content_type=stored_type,
    )

    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO documents(
                id, owner_id, filename, object_key, content_type, byte_size, sha256, uploaded_by,
                source_type, source_ref, source_metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            RETURNING *
            """,
            (
                document_id,
                owner_id,
                safe_name,
                object_key,
                stored_type,
                len(raw),
                digest,
                actor,
                source_type,
                source_ref,
                json.dumps(source_metadata or {}),
            ),
        ).fetchone()
        conn.commit()

    enqueue().enqueue("app.jobs.process_document", document_id, job_timeout="15m")
    result = dict(row)
    result["duplicate"] = False
    return result


async def upload(file: UploadFile, actor: str, owner_id: str | None):
    raw = await file.read()
    return store_bytes(
        raw,
        file.filename or "upload.bin",
        file.content_type,
        actor,
        owner_id,
    )


def _validate_zip_entry(info: zipfile.ZipInfo):
    if info.is_dir():
        return

    try:
        safe_name = safe_relative_name(info.filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"ZIP contains unsafe path: {info.filename}",
        ) from exc

    if info.flag_bits & 0x1:
        raise HTTPException(
            status_code=400,
            detail=f"Encrypted ZIP entries are not supported: {safe_name}",
        )

    unix_mode = info.external_attr >> 16
    if unix_mode and stat.S_ISLNK(unix_mode):
        raise HTTPException(
            status_code=400,
            detail=f"ZIP symlinks are not accepted: {safe_name}",
        )


def _extract_zip(
    raw: bytes,
    archive_name: str,
    actor: str,
    owner_id: str | None,
):
    cfg = settings()
    expanded_limit = cfg.zip_max_expanded_mb * 1024 * 1024

    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail=f"Invalid ZIP archive: {archive_name}") from exc

    infos = [info for info in archive.infolist() if not info.is_dir()]

    if len(infos) > cfg.bulk_max_files:
        raise HTTPException(
            status_code=413,
            detail=f"ZIP contains {len(infos)} files; maximum is {cfg.bulk_max_files}",
        )

    expanded_size = sum(info.file_size for info in infos)
    if expanded_size > expanded_limit:
        raise HTTPException(
            status_code=413,
            detail=(
                f"ZIP would expand to {expanded_size / 1024 / 1024:.1f} MB; "
                f"maximum is {cfg.zip_max_expanded_mb} MB"
            ),
        )

    for info in infos:
        _validate_zip_entry(info)

    accepted = []
    skipped = []
    errors = []
    duplicates = []

    for info in infos:
        try:
            name = safe_relative_name(info.filename)
            if is_ignored(name):
                skipped.append({"name": name, "reason": "ignored system/hidden file"})
                continue
            if not is_supported(name):
                skipped.append({"name": name, "reason": "unsupported file type"})
                continue

            # Per-file expansion guard. Extremely high ratios are typical of zip bombs.
            compressed = max(info.compress_size, 1)
            ratio = info.file_size / compressed
            if info.file_size > 2 * 1024 * 1024 and ratio > 250:
                skipped.append({"name": name, "reason": "suspicious compression ratio"})
                continue

            entry_raw = archive.read(info)
            row = store_bytes(
                entry_raw,
                name,
                mimetypes.guess_type(name)[0],
                actor,
                owner_id,
            )
            if row.get("duplicate"):
                duplicates.append({
                    "name": name,
                    "existing_document_id": str(row["id"]),
                })
            else:
                accepted.append(row)
        except HTTPException as exc:
            errors.append({"name": info.filename, "error": str(exc.detail)})
        except Exception as exc:
            errors.append({"name": info.filename, "error": str(exc)})

    archive.close()

    return {
        "archive": archive_name,
        "accepted": accepted,
        "duplicates": duplicates,
        "skipped": skipped,
        "errors": errors,
    }


async def bulk_upload(files: list[UploadFile], actor: str, owner_id: str | None):
    cfg = settings()
    if not files:
        raise HTTPException(status_code=400, detail="No files supplied")
    if len(files) > cfg.bulk_max_files:
        raise HTTPException(
            status_code=413,
            detail=f"Too many uploaded items; maximum is {cfg.bulk_max_files}",
        )

    total_limit = cfg.bulk_max_total_mb * 1024 * 1024
    total_received = 0

    accepted = []
    duplicates = []
    skipped = []
    errors = []
    archives = []

    for file in files:
        submitted_name = file.filename or "upload.bin"

        try:
            safe_name = safe_relative_name(submitted_name)
        except ValueError:
            errors.append({"name": submitted_name, "error": "unsafe filename"})
            continue

        if is_ignored(safe_name):
            skipped.append({"name": safe_name, "reason": "ignored system/hidden file"})
            continue

        raw = await file.read()
        total_received += len(raw)
        if total_received > total_limit:
            raise HTTPException(
                status_code=413,
                detail=f"Bulk upload exceeds {cfg.bulk_max_total_mb} MB total limit",
            )

        if PurePosixPath(safe_name).suffix.lower() == ".zip":
            result = _extract_zip(raw, safe_name, actor, owner_id)
            archives.append({
                "name": safe_name,
                "accepted": len(result["accepted"]),
                "duplicates": len(result["duplicates"]),
                "skipped": len(result["skipped"]),
                "errors": len(result["errors"]),
            })
            accepted.extend(result["accepted"])
            duplicates.extend(result["duplicates"])
            skipped.extend(
                {"name": f"{safe_name}/{item['name']}", "reason": item["reason"]}
                for item in result["skipped"]
            )
            errors.extend(
                {"name": f"{safe_name}/{item['name']}", "error": item["error"]}
                for item in result["errors"]
            )
            continue

        if not is_supported(safe_name):
            skipped.append({"name": safe_name, "reason": "unsupported file type"})
            continue

        try:
            row = store_bytes(
                raw,
                safe_name,
                file.content_type,
                actor,
                owner_id,
            )
            if row.get("duplicate"):
                duplicates.append({
                    "name": safe_name,
                    "existing_document_id": str(row["id"]),
                })
            else:
                accepted.append(row)
        except HTTPException as exc:
            errors.append({"name": safe_name, "error": str(exc.detail)})
        except Exception as exc:
            errors.append({"name": safe_name, "error": str(exc)})

    return {
        "summary": {
            "submitted_items": len(files),
            "received_bytes": total_received,
            "documents_queued": len(accepted),
            "duplicates": len(duplicates),
            "skipped": len(skipped),
            "errors": len(errors),
            "archives": len(archives),
        },
        "archives": archives,
        "accepted": accepted,
        "duplicates": duplicates,
        "skipped": skipped,
        "errors": errors,
    }


def list_documents():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, filename, content_type, byte_size, sha256, status,
                   extraction_error, uploaded_by, source_type, source_ref, source_metadata,
                   created_at, processed_at
            FROM documents
            WHERE deleted_at IS NULL
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_document(document_id: str):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id=%s AND deleted_at IS NULL",
            (document_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)


def search_chunks(query: str, limit: int):
    qvec = embed_literal(query)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT dc.id, dc.document_id, d.filename, dc.chunk_index, dc.content,
                   1 - (dc.embedding <=> %s::vector) AS semantic_score,
                   ts_rank_cd(dc.search_vector, websearch_to_tsquery('english', %s)) AS lexical_score
            FROM document_chunks dc
            JOIN documents d ON d.id=dc.document_id
            WHERE d.deleted_at IS NULL AND d.status='ready' AND dc.embedding IS NOT NULL
            ORDER BY (
                (1 - (dc.embedding <=> %s::vector)) * 0.85 +
                LEAST(ts_rank_cd(dc.search_vector, websearch_to_tsquery('english', %s)), 1.0) * 0.15
            ) DESC
            LIMIT %s
            """,
            (qvec, query, qvec, query, limit),
        ).fetchall()

    out = []
    for row in rows:
        item = dict(row)
        item["semantic_score"] = float(item["semantic_score"] or 0)
        item["lexical_score"] = float(item["lexical_score"] or 0)
        item["result_type"] = "document_chunk"
        out.append(item)
    return out
