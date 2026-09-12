import io
from pathlib import Path
from tempfile import NamedTemporaryFile

from docx import Document
from pypdf import PdfReader

from app.config import settings
from app.database import connect
from app.documents import minio_client
from app.embeddings import embed_literal


def extract_text(filename: str, raw: bytes) -> str:
    suffix = Path(filename).suffix.lower()

    if suffix in {
        ".txt", ".md", ".csv", ".json", ".log", ".yaml", ".yml",
        ".py", ".ps1", ".sh", ".bash", ".js", ".jsx", ".ts", ".tsx",
        ".go", ".rs", ".java", ".cs", ".c", ".cc", ".cpp", ".h", ".hpp",
        ".sql", ".toml", ".ini", ".cfg", ".conf", ".xml", ".html", ".css",
    }:
        return raw.decode("utf-8", errors="replace")

    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(raw))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)

    if suffix == ".docx":
        doc = Document(io.BytesIO(raw))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)

    raise ValueError(f"Unsupported document type: {suffix or 'unknown'}")


def chunks(text: str, target=1400, overlap=220):
    clean = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not clean:
        return []
    output = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + target)
        if end < len(clean):
            boundary = max(clean.rfind("\n", start, end), clean.rfind(". ", start, end))
            if boundary > start + target // 2:
                end = boundary + 1
        output.append(clean[start:end].strip())
        if end >= len(clean):
            break
        start = max(start + 1, end - overlap)
    return [value for value in output if value]


def process_document(document_id: str):
    with connect() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id=%s", (document_id,)).fetchone()
        if not doc:
            return
        conn.execute("UPDATE documents SET status='processing', extraction_error=NULL WHERE id=%s", (document_id,))
        conn.commit()

    response = None
    try:
        response = minio_client().get_object(settings().minio_bucket, doc["object_key"])
        raw = response.read()
        text = extract_text(doc["filename"], raw)
        parts = chunks(text)
        if not parts:
            raise ValueError("No extractable text found")

        with connect() as conn:
            conn.execute("DELETE FROM document_chunks WHERE document_id=%s", (document_id,))
            for index, part in enumerate(parts):
                conn.execute(
                    """
                    INSERT INTO document_chunks(document_id, chunk_index, content, embedding)
                    VALUES (%s,%s,%s,%s::vector)
                    """,
                    (document_id, index, part, embed_literal(part)),
                )
            conn.execute(
                "UPDATE documents SET status='ready', processed_at=now() WHERE id=%s",
                (document_id,),
            )
            conn.commit()

        if doc.get("source_type") in {"browser_capture", "github"}:
            try:
                from app.document_memory_import import create_job
                create_job(
                    document_id,
                    f"system:{doc['source_type']}",
                    str(doc["owner_id"]) if doc["owner_id"] else None,
                )
            except Exception:
                # The source document remains valid even if automatic memory analysis
                # is already queued or temporarily unavailable.
                pass
    except Exception as exc:
        with connect() as conn:
            conn.execute(
                "UPDATE documents SET status='failed', extraction_error=%s, processed_at=now() WHERE id=%s",
                (str(exc)[:4000], document_id),
            )
            conn.commit()
        raise
    finally:
        if response is not None:
            response.close()
            response.release_conn()
