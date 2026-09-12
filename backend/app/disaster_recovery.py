from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.database import connect


def _row(value):
    return dict(value) if value else None


def _age_hours(dt):
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 3600)


def summary() -> dict[str, Any]:
    cfg = settings()

    with connect() as conn:
        latest_postgres = _row(conn.execute(
            """
            SELECT *
            FROM dr_backup_artifacts
            WHERE artifact_type='postgres'
            ORDER BY artifact_created_at DESC NULLS LAST, first_seen_at DESC
            LIMIT 1
            """
        ).fetchone())

        latest_objects = _row(conn.execute(
            """
            SELECT *
            FROM dr_backup_artifacts
            WHERE artifact_type='objects'
            ORDER BY artifact_created_at DESC NULLS LAST, first_seen_at DESC
            LIMIT 1
            """
        ).fetchone())

        latest_restore = _row(conn.execute(
            """
            SELECT *
            FROM dr_restore_tests
            WHERE status IN ('passed','warning','failed')
            ORDER BY completed_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """
        ).fetchone())

        latest_replication = _row(conn.execute(
            """
            SELECT *
            FROM dr_replication_runs
            WHERE status IN ('passed','warning','failed','disabled')
            ORDER BY completed_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """
        ).fetchone())

        disk = _row(conn.execute(
            "SELECT * FROM dr_status WHERE key='backup_disk'"
        ).fetchone())

        monitor = _row(conn.execute(
            "SELECT * FROM dr_status WHERE key='monitor'"
        ).fetchone())

        counts = dict(conn.execute(
            """
            SELECT
              (SELECT count(*) FROM dr_backup_artifacts
               WHERE artifact_type='postgres') AS postgres_artifacts,
              (SELECT count(*) FROM dr_backup_artifacts
               WHERE artifact_type='objects') AS object_artifacts,
              (SELECT count(*) FROM dr_restore_tests
               WHERE status='passed') AS passed_restore_tests,
              (SELECT count(*) FROM dr_restore_tests
               WHERE status='failed') AS failed_restore_tests
            """
        ).fetchone())

    pg_age = _age_hours(latest_postgres["artifact_created_at"]) if latest_postgres else None
    obj_age = _age_hours(latest_objects["artifact_created_at"]) if latest_objects else None
    restore_age = _age_hours(latest_restore["completed_at"]) if latest_restore else None

    checks = []

    pg_ok = bool(
        latest_postgres
        and latest_postgres["integrity_status"] == "verified"
        and pg_age is not None
        and pg_age <= cfg.dr_max_backup_age_hours
    )
    checks.append({
        "key": "postgres",
        "label": "PostgreSQL backup",
        "status": "healthy" if pg_ok else "critical",
        "detail": (
            f"Verified {pg_age:.1f}h ago"
            if pg_ok else
            "No fresh verified PostgreSQL backup"
        ),
    })

    obj_ok = bool(
        latest_objects
        and latest_objects["integrity_status"] == "verified"
        and obj_age is not None
        and obj_age <= cfg.dr_max_backup_age_hours
    )
    checks.append({
        "key": "objects",
        "label": "Object backup",
        "status": "healthy" if obj_ok else "critical",
        "detail": (
            f"Verified {obj_age:.1f}h ago"
            if obj_ok else
            "No fresh verified object backup"
        ),
    })

    if cfg.dr_restore_test_enabled:
        restore_ok = bool(
            latest_restore
            and latest_restore["status"] in {"passed", "warning"}
            and restore_age is not None
            and restore_age <= cfg.dr_restore_test_max_age_hours
        )
        checks.append({
            "key": "restore",
            "label": "Restore test",
            "status": (
                "healthy" if restore_ok and latest_restore["status"] == "passed"
                else "warning" if restore_ok
                else "critical"
            ),
            "detail": (
                f"{latest_restore['status']} {restore_age:.1f}h ago"
                if latest_restore and restore_age is not None
                else "No recent restore test"
            ),
        })
    else:
        restore_ok = True
        checks.append({
            "key": "restore",
            "label": "Restore test",
            "status": "disabled",
            "detail": "Automated restore testing is disabled",
        })

    offsite_enabled = bool((cfg.dr_offsite_remote or "").strip())
    if offsite_enabled:
        replication_ok = bool(
            latest_replication
            and latest_replication["status"] == "passed"
            and _age_hours(latest_replication["completed_at"]) is not None
            and _age_hours(latest_replication["completed_at"]) <= max(
                cfg.dr_offsite_interval_hours * 2,
                cfg.dr_max_backup_age_hours,
            )
        )
        checks.append({
            "key": "offsite",
            "label": "Off-site replication",
            "status": "healthy" if replication_ok else "warning",
            "detail": (
                f"Replicated to {cfg.dr_offsite_remote}"
                if replication_ok
                else f"Configured for {cfg.dr_offsite_remote}, but no recent verified copy"
            ),
        })
    else:
        replication_ok = True
        checks.append({
            "key": "offsite",
            "label": "Off-site replication",
            "status": "disabled",
            "detail": "Not configured",
        })

    disk_ok = False
    if disk and disk.get("details"):
        try:
            disk_ok = float(disk["details"].get("free_gb", 0)) >= cfg.dr_min_backup_free_gb
        except Exception:
            disk_ok = False
    checks.append({
        "key": "disk",
        "label": "Backup filesystem",
        "status": "healthy" if disk_ok else "warning",
        "detail": (
            f"{disk['details'].get('free_gb')} GB free"
            if disk and disk.get("details")
            else "No recent filesystem reading"
        ),
    })

    weights = {
        "postgres": 30,
        "objects": 25,
        "restore": 25,
        "offsite": 10,
        "disk": 10,
    }
    score = 0
    for item in checks:
        weight = weights[item["key"]]
        if item["status"] in {"healthy", "disabled"}:
            score += weight
        elif item["status"] == "warning":
            score += round(weight * 0.5)

    overall = "healthy" if score >= 90 else "warning" if score >= 65 else "critical"

    return {
        "score": score,
        "overall": overall,
        "checks": checks,
        "latest": {
            "postgres": latest_postgres,
            "objects": latest_objects,
            "restore_test": latest_restore,
            "replication": latest_replication,
        },
        "status": {
            "backup_disk": disk,
            "monitor": monitor,
        },
        "counts": counts,
        "config": {
            "max_backup_age_hours": cfg.dr_max_backup_age_hours,
            "restore_test_enabled": cfg.dr_restore_test_enabled,
            "restore_test_interval_hours": cfg.dr_restore_test_interval_hours,
            "restore_test_max_age_hours": cfg.dr_restore_test_max_age_hours,
            "offsite_enabled": offsite_enabled,
            "offsite_remote": cfg.dr_offsite_remote if offsite_enabled else None,
            "offsite_interval_hours": cfg.dr_offsite_interval_hours,
            "retention_days": None,
        },
    }


def artifacts(limit: int = 100):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM dr_backup_artifacts
            ORDER BY artifact_created_at DESC NULLS LAST, first_seen_at DESC
            LIMIT %s
            """,
            (min(max(limit, 1), 500),),
        ).fetchall()
    return [dict(row) for row in rows]


def restore_tests(limit: int = 50):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.*,
                   p.file_name AS postgres_file_name,
                   o.file_name AS object_file_name
            FROM dr_restore_tests t
            LEFT JOIN dr_backup_artifacts p ON p.id=t.postgres_artifact_id
            LEFT JOIN dr_backup_artifacts o ON o.id=t.object_artifact_id
            ORDER BY t.created_at DESC
            LIMIT %s
            """,
            (min(max(limit, 1), 200),),
        ).fetchall()
    return [dict(row) for row in rows]


def replication_runs(limit: int = 50):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM dr_replication_runs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (min(max(limit, 1), 200),),
        ).fetchall()
    return [dict(row) for row in rows]


def queue_request(action: str, actor: str):
    if action not in {"scan", "restore_test", "replicate"}:
        raise ValueError("Unsupported disaster recovery action")

    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO dr_requests(action, requested_by)
            VALUES (%s,%s)
            RETURNING *
            """,
            (action, actor),
        ).fetchone()
        conn.commit()
    return dict(row)


def recent_requests(limit: int = 30):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM dr_requests
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (min(max(limit, 1), 100),),
        ).fetchall()
    return [dict(row) for row in rows]
