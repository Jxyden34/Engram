"""Optional Telegram delivery. The server token is never returned through the API."""
import re

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.database import connect


class TelegramSettings(BaseModel):
    enabled: bool = False
    chat_id: str = Field(pattern=r"^-?[0-9]{1,20}$")


def configuration():
    with connect() as conn:
        row = conn.execute("SELECT enabled,chat_id FROM notification_telegram").fetchone()
        deliveries = conn.execute("""
            SELECT count(*) FILTER (WHERE delivered_at IS NOT NULL) AS delivered,
              count(*) FILTER (WHERE delivered_at IS NULL AND attempts>0) AS retrying
            FROM notification_deliveries
        """).fetchone()
    return {**(dict(row) if row else {"enabled": False, "chat_id": ""}),
            "available": bool(settings().telegram_bot_token),
            "delivered": deliveries["delivered"], "retrying": deliveries["retrying"]}


def configure(data: TelegramSettings):
    if data.enabled and not settings().telegram_bot_token:
        raise HTTPException(status_code=503, detail="Configure TELEGRAM_BOT_TOKEN on the server first")
    with connect() as conn:
        conn.execute("""
            INSERT INTO notification_telegram(chat_id,enabled) VALUES (%s,%s)
            ON CONFLICT(project_id) DO UPDATE SET chat_id=EXCLUDED.chat_id,
              enabled=EXCLUDED.enabled,updated_at=now()
        """, (data.chat_id, data.enabled))
        conn.commit()
    return configuration()


def send(chat_id: str, text: str):
    token = settings().telegram_bot_token
    if not token:
        raise HTTPException(status_code=503, detail="Telegram bot is not configured")
    if not re.fullmatch(r"-?[0-9]{1,20}", chat_id):
        raise HTTPException(status_code=422, detail="Invalid Telegram chat ID")
    try:
        # Fixed Telegram origin. No proxy inheritance or redirect to another host.
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                "chat_id": chat_id, "text": text[:4000],
                "link_preview_options": {"is_disabled": True},
                "protect_content": True,
            })
            if response.is_error or not response.json().get("ok"):
                raise HTTPException(status_code=502, detail="Telegram rejected delivery. Check the bot and chat permissions.")
    except (httpx.HTTPError, ValueError):
        # HTTP exceptions include the token-bearing URL, so expose a generic failure.
        raise HTTPException(status_code=502, detail="Telegram delivery failed. Check connectivity and chat permissions.") from None


def test_delivery():
    config = configuration()
    if not config["enabled"]:
        raise HTTPException(status_code=409, detail="Enable and save the Telegram destination first")
    send(config["chat_id"], "Engram notification delivery is connected. This is a test message.")
    return {"sent": True}


def deliver():
    if not settings().telegram_bot_token:
        return
    # Hold one project delivery lock through the bounded HTTP sends to avoid concurrent sends.
    with connect(timeout=5) as conn:
        if not conn.execute("SELECT pg_try_advisory_xact_lock(hashtextextended('telegram:' || engram_current_project()::text, 0)) AS locked").fetchone()["locked"]:
            return
        config = conn.execute("SELECT chat_id FROM notification_telegram WHERE enabled").fetchone()
        if not config:
            return
        conn.execute("""
            INSERT INTO notification_deliveries(project_id,notification_id,generation)
            SELECT project_id,id,generation FROM notifications WHERE resolved_at IS NULL
            ON CONFLICT DO NOTHING
        """)
        rows = conn.execute("""
            SELECT d.notification_id,d.generation,d.attempts,n.title,n.detail,n.href,n.severity
            FROM notification_deliveries d JOIN notifications n ON n.id=d.notification_id
            WHERE d.delivered_at IS NULL AND d.attempts<5 AND d.next_attempt_at<=now()
              AND n.resolved_at IS NULL AND d.generation=n.generation
            ORDER BY n.created_at LIMIT 10 FOR UPDATE OF d SKIP LOCKED
        """).fetchall()
        for row in rows:
            try:
                send(config["chat_id"], f'Engram · {row["severity"]}\n{row["title"]}\n{row["detail"]}\n{settings().public_origin.rstrip("/")}{row["href"]}')
            except HTTPException:
                conn.execute("""
                    UPDATE notification_deliveries SET attempts=attempts+1,
                      next_attempt_at=now()+(power(2,attempts)*60)*interval '1 second',
                      last_error='Telegram delivery failed'
                    WHERE notification_id=%s AND generation=%s
                """, (row["notification_id"], row["generation"]))
            else:
                conn.execute("""
                    UPDATE notification_deliveries SET attempts=attempts+1,delivered_at=now(),last_error=NULL
                    WHERE notification_id=%s AND generation=%s
                """, (row["notification_id"], row["generation"]))
        conn.commit()
