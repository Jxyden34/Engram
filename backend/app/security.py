import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from typing import Iterable

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request

from app.config import settings
from app.database import connect


SESSION_COOKIE = "memory_session"
CSRF_COOKIE = "memory_csrf"
ph = PasswordHasher()


@dataclass
class Principal:
    actor: str
    user_id: str | None
    username: str | None
    is_admin: bool
    scopes: set[str]
    auth_type: str


ADMIN_SCOPES = {
    "memory:read",
    "memory:write",
    "memory:delete_request",
    "memory:delete_approve",
    "document:read",
    "document:write",
    "audit:read",
    "keys:admin",
    "mcp:use",
    "capture:write",
    "connector:admin",
    "oauth:admin",
}


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def client_ip(request: Request) -> str | None:
    candidate = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "")
    )
    if not candidate:
        return None
    try:
        return str(ip_address(candidate))
    except ValueError:
        return None


def create_session(user_id: str, request: Request) -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=settings().session_ttl_hours)

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions(user_id, token_hash, csrf_hash, ip_address, user_agent, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                sha256(token),
                sha256(csrf),
                client_ip(request),
                request.headers.get("user-agent", "")[:1000],
                expires,
            ),
        )
        conn.commit()
    return token, csrf


def revoke_session(token: str | None):
    if not token:
        return
    with connect() as conn:
        conn.execute(
            "UPDATE sessions SET revoked_at = now() WHERE token_hash = %s AND revoked_at IS NULL",
            (sha256(token),),
        )
        conn.commit()


def session_principal(token: str) -> Principal | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT s.id AS session_id, u.id AS user_id, u.username, u.is_admin, u.is_active
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = %s
              AND s.revoked_at IS NULL
              AND s.expires_at > now()
            """,
            (sha256(token),),
        ).fetchone()
        if not row or not row["is_active"]:
            return None
        conn.execute("UPDATE sessions SET last_seen_at = now() WHERE id = %s", (row["session_id"],))
        conn.commit()

    return Principal(
        actor=f"user:{row['username']}",
        user_id=str(row["user_id"]),
        username=row["username"],
        is_admin=bool(row["is_admin"]),
        scopes=set(ADMIN_SCOPES) if row["is_admin"] else {"memory:read", "memory:write", "document:read"},
        auth_type="session",
    )


def api_key_principal(token: str) -> Principal | None:
    token_hash = sha256(token)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, owner_id, name, scopes
            FROM api_keys
            WHERE key_hash = %s AND revoked_at IS NULL
            """,
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE api_keys SET last_used_at = now() WHERE id = %s", (row["id"],))
        conn.commit()

    return Principal(
        actor=f"api:{row['name']}",
        user_id=str(row["owner_id"]) if row["owner_id"] else None,
        username=None,
        is_admin=False,
        scopes=set(row["scopes"]),
        auth_type="api_key",
    )


def bearer_principal(token: str, expected_resource: str | None = None) -> Principal | None:
    if token.startswith("mb_at_"):
        from app.oauth import oauth_access_token_principal
        return oauth_access_token_principal(token, expected_resource)
    return api_key_principal(token)


def authenticate(request: Request) -> Principal:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
        if bearer.startswith("mb_at_") and not request.url.path.startswith("/mcp"):
            principal = None
        else:
            principal = bearer_principal(bearer)
    else:
        principal = session_principal(request.cookies.get(SESSION_COOKIE, "")) if request.cookies.get(SESSION_COOKIE) else None

    if not principal:
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


def require(request: Request, *scopes: str) -> Principal:
    principal = authenticate(request)
    missing = [scope for scope in scopes if scope not in principal.scopes]
    if missing:
        raise HTTPException(status_code=403, detail=f"Missing scope(s): {', '.join(missing)}")
    return principal


def validate_csrf(request: Request):
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    if request.url.path in {"/api/v1/auth/login"}:
        return
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return

    session_token = request.cookies.get(SESSION_COOKIE)
    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    csrf_header = request.headers.get("x-csrf-token")
    if not session_token or not csrf_cookie or not csrf_header:
        raise HTTPException(status_code=403, detail="CSRF token required")
    if not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF token mismatch")

    with connect() as conn:
        row = conn.execute(
            """
            SELECT csrf_hash
            FROM sessions
            WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > now()
            """,
            (sha256(session_token),),
        ).fetchone()
    if not row or not hmac.compare_digest(row["csrf_hash"], sha256(csrf_cookie)):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def generate_api_key() -> tuple[str, str, str]:
    token = "mem_live_" + secrets.token_urlsafe(40)
    return token, token[:18], sha256(token)


def validate_csrf_value(session_token: str | None, csrf_cookie: str | None, submitted: str | None):
    if not session_token or not csrf_cookie or not submitted:
        raise HTTPException(status_code=403, detail="CSRF token required")
    if not hmac.compare_digest(csrf_cookie, submitted):
        raise HTTPException(status_code=403, detail="CSRF token mismatch")

    with connect() as conn:
        row = conn.execute(
            """
            SELECT csrf_hash
            FROM sessions
            WHERE token_hash=%s AND revoked_at IS NULL AND expires_at > now()
            """,
            (sha256(session_token),),
        ).fetchone()
    if not row or not hmac.compare_digest(row["csrf_hash"], sha256(csrf_cookie)):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
