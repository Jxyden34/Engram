import re
from datetime import datetime, timezone
from uuid import uuid4

from app.config import settings
from app.database import connect
from app.documents import store_bytes


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
    return (clean or "capture")[:120]


def create_capture(data: dict, actor: str, owner_id: str | None):
    cfg = settings()
    text = str(data["text"]).strip()
    if len(text) > cfg.capture_max_chars:
        text = text[: cfg.capture_max_chars]

    title = str(data["title"]).strip()
    url = str(data.get("url") or "").strip() or None
    capture_type = data.get("capture_type") or "page"
    captured_at = datetime.now(timezone.utc)

    front = [
        f"# {title}",
        "",
        f"- Capture type: {capture_type}",
        f"- Captured at: {captured_at.isoformat()}",
    ]
    if url:
        front.append(f"- Source URL: {url}")

    body = "\n".join(front) + "\n\n" + text + "\n"
    filename = (
        f"browser/{captured_at.strftime('%Y/%m/%d')}/"
        f"{_slug(title)}-{captured_at.strftime('%H%M%S')}-{str(uuid4())[:8]}.md"
    )

    document = store_bytes(
        body.encode("utf-8"),
        filename,
        "text/markdown",
        actor,
        owner_id,
        source_type="browser_capture",
        source_ref=url,
        source_metadata={
            "capture_type": capture_type,
            "title": title,
            "url": url,
            "captured_at": captured_at.isoformat(),
            **(data.get("metadata") or {}),
        },
        dedupe=False,
    )

    with connect() as conn:
        capture = conn.execute(
            """
            INSERT INTO browser_captures(
                owner_id, document_id, capture_type, title, url, created_by
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                owner_id,
                document["id"],
                capture_type,
                title,
                url,
                actor,
            ),
        ).fetchone()
        conn.commit()

    result = dict(capture)
    result["document"] = document
    return result
