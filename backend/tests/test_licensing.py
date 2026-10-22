from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

from app import licensing
from scripts.commercial_license import issue, write_new


@pytest.fixture
def issuer(tmp_path, monkeypatch):
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "public.pem"
    write_new(public_path, private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    monkeypatch.setattr(licensing, "settings", lambda: SimpleNamespace(commercial_license_public_key_path=str(public_path)))
    return private


def test_issued_key_is_signed_scoped_and_time_limited(issuer, tmp_path):
    installation = str(uuid4())
    key = issue(issuer, installation, "Example Ltd", (datetime.now(timezone.utc) + timedelta(days=2)).date())
    result = licensing.validate_key(key, installation)
    assert result["state"] == "active" and result["customer"] == "Example Ltd"
    with pytest.raises(ValueError, match="mismatch"):
        licensing.validate_key(key, str(uuid4()))
    token_path = tmp_path / "customer.license"
    write_new(token_path, key.encode())
    with pytest.raises(FileExistsError):
        write_new(token_path, b"replacement")
    assert token_path.read_text() == key


@pytest.mark.parametrize("change", ["expired", "tampered", "issuer", "audience", "plan", "malformed_id", "no_expiry", "wrong_signer", "symmetric"])
def test_untrusted_keys_are_rejected(issuer, change):
    installation = str(uuid4())
    now = int(datetime.now(timezone.utc).timestamp())
    claims = {"iss": licensing.ISSUER, "aud": licensing.AUDIENCE, "iat": now - 60,
              "exp": now + 3600, "jti": str(uuid4()), "customer": "Example Ltd",
              "plan": "commercial", "installation_id": installation}
    signing_key, algorithm = issuer, "EdDSA"
    if change == "expired": claims["exp"] = now - 1
    if change == "issuer": claims["iss"] = "someone-else"
    if change == "audience": claims["aud"] = "another-product"
    if change == "plan": claims["plan"] = "personal"
    if change == "malformed_id": claims["jti"] = ["not-a-uuid"]
    if change == "no_expiry": del claims["exp"]
    if change == "wrong_signer": signing_key = Ed25519PrivateKey.generate()
    if change == "symmetric": signing_key, algorithm = b"x" * 32, "HS256"
    token = jwt.encode(claims, signing_key, algorithm=algorithm)
    if change == "tampered":
        header, payload, signature = token.split(".")
        token = header + "." + payload[:-3] + "AAA." + signature
    with pytest.raises(ValueError):
        licensing.validate_key(licensing.PREFIX + token, installation)


def test_expired_commercial_mode_keeps_read_and_recovery_paths(monkeypatch):
    monkeypatch.setattr(licensing, "status", lambda: {"mode": "commercial", "state": "unlicensed"})
    with pytest.raises(HTTPException) as error:
        licensing.require_commercial_license()
    assert error.value.status_code == 402
    for method, path in [("GET", "/api/v1/memories"), ("POST", "/api/v1/search"),
                         ("PUT", "/api/v1/license/"), ("POST", "/api/v1/dr/restore-test")]:
        assert not licensing.is_product_write(method, path)
    assert licensing.is_product_write("POST", "/api/v1/memories")
    monkeypatch.setattr(licensing, "status", lambda: {"mode": "personal", "state": "personal"})
    licensing.require_commercial_license()


def test_license_activation_http_persistence_and_expiry(issuer):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import connect
    from app.security import hash_password

    username, password = "licence-" + uuid4().hex[:12], "test-" + uuid4().hex
    with connect() as conn:
        original = conn.execute("SELECT * FROM commercial_license WHERE singleton").fetchone()
        user = conn.execute("INSERT INTO users(username,password_hash,is_admin) VALUES (%s,%s,true) RETURNING id",
                            (username, hash_password(password))).fetchone()["id"]
        conn.commit()
    try:
        client = TestClient(app)
        assert client.get('/api/v1/license').status_code == 401
        login = client.post('/api/v1/mobile/login', json={"username": username, "password": password})
        headers = {"Authorization": "Bearer " + login.json()["token"]}
        assert client.put('/api/v1/license', headers=headers, json={"mode": "personal"}).status_code == 200
        installation = client.get('/api/v1/license', headers=headers).json()["installation_id"]
        key = issue(issuer, installation, "Example Ltd", (datetime.now(timezone.utc) + timedelta(days=1)).date())
        result = client.put('/api/v1/license', headers=headers, json={"mode": "commercial", "license_key": key})
        assert result.status_code == 200 and result.json()["state"] == "active"
        assert key not in result.text and "license_key" not in result.json()
        assert client.get('/api/v1/license', headers=headers).json()["customer"] == "Example Ltd"
        assert client.put('/api/v1/license', headers=headers, json={"mode": "commercial", "license_key": "forged"}).status_code == 400
        assert client.get('/api/v1/license', headers=headers).json()["state"] == "active"
        with connect() as conn:
            conn.execute("UPDATE users SET is_admin=false WHERE id=%s", (user,)); conn.commit()
        assert client.get('/api/v1/license', headers=headers).status_code == 403
        assert client.put('/api/v1/license', headers=headers, json={"mode": "personal"}).status_code == 403
        with connect() as conn:
            conn.execute("UPDATE users SET is_admin=true WHERE id=%s", (user,))
            conn.execute("UPDATE commercial_license SET license_key='invalid' WHERE singleton"); conn.commit()
        assert client.post('/api/v1/memories', headers=headers, json={}).status_code == 402
        assert client.get('/api/v1/memories', headers=headers).status_code == 200
        assert client.get('/health').status_code == 200
        assert client.put('/api/v1/license', headers=headers, json={"mode": "commercial", "license_key": key}).status_code == 200
        with connect() as conn:
            records = conn.execute("SELECT new_data FROM audit_log WHERE actor=%s AND action='license.update'", (f"user:{username}",)).fetchall()
            assert records and all("license_key" not in (r["new_data"] or {}) for r in records)
    finally:
        with connect() as conn:
            conn.execute("UPDATE commercial_license SET use_mode=%s, license_key=%s, updated_by=%s, updated_at=%s WHERE singleton",
                         (original["use_mode"], original["license_key"], original["updated_by"], original["updated_at"]))
            conn.execute("DELETE FROM audit_log WHERE actor=%s", (f"user:{username}",))
            conn.execute("DELETE FROM sessions WHERE user_id=%s", (user,))
            conn.execute("DELETE FROM users WHERE id=%s", (user,)); conn.commit()
