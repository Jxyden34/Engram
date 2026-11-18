"""Project notifications derived from existing review and operational state."""
from uuid import UUID

from fastapi import HTTPException

from app.database import connect, current_project_id, project_scope, DEFAULT_PROJECT_ID
from app import disaster_recovery


def collect(conn):
    items = []

    def add(kind, key, title, detail, href, severity="warning"):
        items.append(dict(kind=kind, source_key=str(key), title=title, detail=detail, href=href, severity=severity))

    for row in conn.execute("""
        SELECT id FROM connectors WHERE enabled AND last_status='failed'
        ORDER BY last_sync_at DESC NULLS LAST LIMIT 100
    """):
        add("connector_failure", row["id"], "Connector sync failed",
            "Review the connector's latest run and authorization.", "/connectors")

    for row in conn.execute("""
        SELECT DISTINCT m.id FROM memories m
        JOIN (
          SELECT nearest_memory_id FROM candidate_memories WHERE status='pending' AND comparison='conflicts'
          UNION SELECT nearest_memory_id FROM document_candidate_memories WHERE status='pending' AND comparison='conflicts'
        ) c ON c.nearest_memory_id=m.id
        WHERE m.importance>=8 AND m.deleted_at IS NULL AND m.archived_at IS NULL
          AND (m.valid_to IS NULL OR m.valid_to>now())
        ORDER BY m.id LIMIT 100
    """):
        add("important_conflict", row["id"], "Important memory needs conflict review",
            "An imported candidate contradicts a memory with importance 8 or higher.", "/imports")

    for row in conn.execute("""
        SELECT m.id, m.updated_at FROM memories m
        JOIN LATERAL (
          SELECT snapshot FROM memory_versions WHERE memory_id=m.id ORDER BY version_no DESC LIMIT 1
        ) v ON true
        WHERE m.importance>=8 AND m.deleted_at IS NULL AND m.archived_at IS NULL
          AND (m.valid_to IS NULL OR m.valid_to>now())
          AND m.updated_at>now()-interval '30 days'
          AND (m.content IS DISTINCT FROM v.snapshot->>'content'
            OR m.title IS DISTINCT FROM v.snapshot->>'title'
)
        ORDER BY m.updated_at DESC LIMIT 100
    """):
        add("important_update", f'{row["id"]}:{row["updated_at"].isoformat()}',
            "Important memory updated", "Review the changed facts and their version history.",
            f'/memories/{row["id"]}', "info")

    # Superseding creates a new memory rather than modifying the old version.
    for row in conn.execute("""
        SELECT id FROM memories WHERE supersedes_memory_id IS NOT NULL AND importance>=8
          AND deleted_at IS NULL AND archived_at IS NULL AND created_at>now()-interval '30 days'
          AND (valid_to IS NULL OR valid_to>now())
        ORDER BY created_at DESC LIMIT 100
    """):
        add("important_update", f'supersedes:{row["id"]}', "Important fact superseded",
            "A new memory replaces earlier information. Review its source and history.",
            f'/memories/{row["id"]}', "info")

    for row in conn.execute("""
        SELECT id FROM memories
        WHERE deleted_at IS NULL AND archived_at IS NULL
          AND (valid_to IS NULL OR valid_to>now())
          AND updated_at<now()-interval '180 days'
          AND (memory_type IN ('credential','credentials') OR
            tags && ARRAY['credential','credentials','password','api-key','access-token']::text[])
        ORDER BY updated_at LIMIT 100
    """):
        add("stale_credentials", row["id"], "Credential documentation needs review",
            "A memory tagged as credential documentation has not been updated for 180 days.",
            f'/memories/{row["id"]}')

    row = conn.execute("""
        SELECT (SELECT count(*) FROM candidate_memories WHERE status='pending' AND created_at<now()-interval '7 days')
          + (SELECT count(*) FROM document_candidate_memories WHERE status='pending' AND created_at<now()-interval '7 days') AS n
    """).fetchone()
    if row["n"]:
        add("unresolved_candidates", "inbox", "Candidates are waiting for review",
            f'{row["n"]} candidates have been pending for at least seven days.', "/imports", "info")

    # Backup artifacts describe the entire deployment, so show them only in Personal.
    if current_project_id() == DEFAULT_PROJECT_ID:
        for check in disaster_recovery.summary()["checks"]:
            if check["key"] in {"postgres", "objects"} and check["status"] != "healthy":
                add("backup_failure", check["key"], f'{check["label"]} needs attention',
                    check["detail"], "/disaster-recovery", "critical")
    return items


def refresh():
    with connect(timeout=5) as conn:
        conn.execute("SET LOCAL statement_timeout='10s'")
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                     ("notifications:" + current_project_id(),))
        items = collect(conn)
        active = []
        for item in items:
            row = conn.execute("""
                INSERT INTO notifications(kind,source_key,title,detail,href,severity)
                VALUES (%(kind)s,%(source_key)s,%(title)s,%(detail)s,%(href)s,%(severity)s)
                ON CONFLICT(project_id,kind,source_key) DO UPDATE SET
                  title=EXCLUDED.title,detail=EXCLUDED.detail,href=EXCLUDED.href,severity=EXCLUDED.severity,
                  last_seen_at=now(),resolved_at=NULL,
                  created_at=CASE WHEN notifications.resolved_at IS NOT NULL THEN now() ELSE notifications.created_at END,
                  generation=notifications.generation+CASE WHEN notifications.resolved_at IS NOT NULL THEN 1 ELSE 0 END
                RETURNING id
            """, item).fetchone()
            active.append(row["id"])
        conn.execute("""
            UPDATE notifications SET resolved_at=now()
            WHERE resolved_at IS NULL AND NOT (id=ANY(%s::uuid[]))
        """, (active,))
        conn.execute("DELETE FROM notifications WHERE resolved_at<now()-interval '90 days'")
        conn.commit()


def inbox(user_id, *, dismissed=False):
    with connect() as conn:
        rows = conn.execute("""
            SELECT n.*,r.read_at,r.dismissed_at FROM notifications n
            LEFT JOIN notification_receipts r ON r.notification_id=n.id
              AND r.user_id=%s AND r.generation=n.generation
            WHERE n.resolved_at IS NULL AND (%s OR r.dismissed_at IS NULL)
            ORDER BY CASE n.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
              n.created_at DESC LIMIT 200
        """, (user_id, dismissed)).fetchall()
        count = conn.execute("""
            SELECT count(*) AS n FROM notifications n
            LEFT JOIN notification_receipts r ON r.notification_id=n.id
              AND r.user_id=%s AND r.generation=n.generation
            WHERE n.resolved_at IS NULL AND r.read_at IS NULL AND r.dismissed_at IS NULL
        """, (user_id,)).fetchone()["n"]
    return {"items": [dict(row) for row in rows], "unread": count}


def mark(notification_id, user_id, *, dismiss=False):
    UUID(notification_id)
    with connect() as conn:
        row = conn.execute("""
            INSERT INTO notification_receipts(project_id,notification_id,user_id,generation,read_at,dismissed_at)
            SELECT project_id,id,%s,generation,now(),CASE WHEN %s THEN now() END
            FROM notifications WHERE id=%s AND resolved_at IS NULL
            ON CONFLICT(project_id,notification_id,user_id) DO UPDATE SET
              generation=EXCLUDED.generation,read_at=EXCLUDED.read_at,
              dismissed_at=CASE WHEN %s THEN now() ELSE NULL END
            RETURNING notification_id
        """, (user_id, dismiss, notification_id, dismiss)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Notification not found")
        conn.commit()
    return {"id": str(row["notification_id"])}


def refresh_all():
    with connect() as conn:
        projects = [str(row["id"]) for row in conn.execute("SELECT id FROM projects")]
    for project in projects:
        try:
            with project_scope(project):
                refresh()
                from app.telegram_notifications import deliver
                deliver()
        except Exception:
            # A failed project must not prevent connector scheduling or other projects.
            import logging
            logging.getLogger(__name__).exception("Notification refresh failed for project %s", project)
