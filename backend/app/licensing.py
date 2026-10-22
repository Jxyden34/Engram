"""Common edition API. Personal Community never requires a key; business use requires Commercial."""
from fastapi import HTTPException
from app.edition import get_edition
from app.config import settings

PREFIX = "ENGRAM-C1."
ISSUER = "engram-commercial"
AUDIENCE = "engram-self-hosted"


def status() -> dict:
    if get_edition() == "community":
        return {"edition": "community", "mode": "community", "state": "free", "locked": False,
                "installation_id": None, "customer": None, "license_id": None, "expires_at": None,
                "purchase_url": None}
    from app.commercial.licensing import status as commercial_status
    result = commercial_status()
    return {**result, "edition": "commercial", "locked": result["state"] != "active",
            "purchase_url": settings().commercial_license_purchase_url}


def public_status() -> dict:
    current = status()
    return {k: current[k] for k in ("edition", "state", "locked", "installation_id", "purchase_url", "expires_at")}


def activate(mode: str, key: str | None, actor: str) -> dict:
    if get_edition() == "community":
        raise HTTPException(400, "Community is free and does not need a licence key")
    from app.commercial.licensing import activate as commercial_activate
    commercial_activate(mode, key, actor)
    return status()


def require_commercial_license():
    if get_edition() == "commercial":
        from app.commercial.licensing import require_commercial_license as require_key
        require_key()


def is_product_request(path: str) -> bool:
    path = path.rstrip("/")
    if path == "/mcp" or path.startswith("/mcp/"):
        return True
    return path.startswith("/api/v1/") and path not in {
        "/api/v1/license", "/api/v1/edition", "/api/v1/branding", "/api/v1/auth/login", "/api/v1/auth/logout",
        "/api/v1/auth/me", "/api/v1/mobile/login", "/api/v1/mobile/logout",
    }
