"""Offline commercial entitlements; keep the issuer's private key off servers."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException

from app.config import settings
from app.database import connect

PREFIX = "ENGRAM-C1."
ISSUER = "engram-commercial"
AUDIENCE = "engram-self-hosted"


def validate_key(key: str, installation_id: str) -> dict:
    if not key.startswith(PREFIX) or len(key) > 8192:
        raise ValueError("Invalid commercial licence key")
    try:
        public_key = serialization.load_pem_public_key(
            Path(settings().commercial_license_public_key_path).read_bytes())
    except (OSError, ValueError) as exc:
        raise ValueError("Commercial licence verification is not configured") from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("Commercial verification requires an Ed25519 public key")
    try:
        claims = jwt.decode(key[len(PREFIX):], public_key, algorithms=["EdDSA"],
                            issuer=ISSUER, audience=AUDIENCE, options={"require": [
                                "iss", "aud", "exp", "iat", "jti", "customer", "plan", "installation_id"]})
        if not isinstance(claims["jti"], str):
            raise ValueError()
        UUID(claims["jti"])
        if (claims["installation_id"] != installation_id or claims["plan"] != "commercial"
                or type(claims["exp"]) is not int or type(claims["iat"]) is not int
                or claims["exp"] <= claims["iat"] or not isinstance(claims["customer"], str)
                or not 1 <= len(claims["customer"].strip()) <= 200):
            raise ValueError()
        expires = datetime.fromtimestamp(claims["exp"], timezone.utc).isoformat()
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Commercial licence has expired") from exc
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, OverflowError, OSError) as exc:
        raise ValueError("Invalid commercial licence or installation mismatch") from exc
    return {"state": "active", "customer": claims["customer"],
            "license_id": claims["jti"], "expires_at": expires}


def status() -> dict:
    with connect() as conn:
        row = conn.execute("SELECT installation_id, use_mode, license_key FROM commercial_license WHERE singleton").fetchone()
    result = {"installation_id": str(row["installation_id"]), "mode": row["use_mode"],
              "state": "personal", "customer": None, "license_id": None, "expires_at": None}
    if row["use_mode"] == "commercial":
        try:
            result.update(validate_key(row["license_key"] or "", result["installation_id"]))
        except ValueError as exc:
            result.update(state="unlicensed", message=str(exc))
    return result


def activate(mode: str, key: str | None, actor: str) -> dict:
    if mode not in {"personal", "commercial"}:
        raise HTTPException(400, "Invalid use mode")
    with connect() as conn:
        row = conn.execute("SELECT installation_id, license_key FROM commercial_license WHERE singleton FOR UPDATE").fetchone()
        token = (key or row["license_key"] or "").strip() if mode == "commercial" else None
        if mode == "commercial":
            try:
                validate_key(token, str(row["installation_id"]))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        conn.execute("""UPDATE commercial_license SET use_mode=%s, license_key=%s,
                        updated_by=%s, updated_at=now() WHERE singleton""", (mode, token, actor))
        conn.commit()
    return status()


def require_commercial_license():
    current = status()
    if current["mode"] == "commercial" and current["state"] != "active":
        raise HTTPException(402, "A valid paid commercial licence is required. Renew it in Settings; existing data remains readable.")


def is_product_write(method: str, path: str) -> bool:
    path = path.rstrip("/")
    if method not in {"POST", "PUT", "PATCH", "DELETE"} or not path.startswith("/api/v1/"):
        return False
    if path.startswith(("/api/v1/auth/", "/api/v1/mobile/", "/api/v1/dr/")):
        return False
    return path not in {
        "/api/v1/license", "/api/v1/search", "/api/v1/projects/search", "/api/v1/ask",
        "/api/v1/intelligence/context", "/api/v1/intelligence/compare", "/api/v1/intelligence/reflect",
    }
