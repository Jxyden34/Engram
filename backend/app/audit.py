from fastapi import Request
from app.database import connect
from app.security import client_ip
from app.util import json_text


def log(
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    request: Request | None = None,
    reason: str | None = None,
    old_data=None,
    new_data=None,
):
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_log(actor, action, entity_type, entity_id, ip_address, reason, old_data, new_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                actor,
                action,
                entity_type,
                entity_id,
                client_ip(request) if request else None,
                reason,
                json_text(old_data) if old_data is not None else None,
                json_text(new_data) if new_data is not None else None,
            ),
        )
        conn.commit()
