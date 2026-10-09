import base64
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app import connectors


def test_gmail_token_ciphertext_format_and_connector_binding():
    config = SimpleNamespace(
        google_token_encryption_key=base64.b64encode(bytes(32)).decode("ascii")
    )
    # Fixed AES-256-GCM vector: zero key/nonce, connector-test AAD, legacy-token.
    stored = "AAAAAAAAAAAAAAAAosInXC4ZRhpoJaC9NzaoEQ34gsuHJIrVEOCLqQ=="
    with patch.object(connectors, "settings", return_value=config):
        assert connectors._decrypt_google_token(stored, "connector-test") == "legacy-token"
        fresh = connectors._encrypt_google_token("new-token", "connector-test")
        assert connectors._decrypt_google_token(fresh, "connector-test") == "new-token"
        assert fresh != connectors._encrypt_google_token("new-token", "connector-test")
        with pytest.raises(InvalidTag):
            connectors._decrypt_google_token(stored, "another-connector")
        corrupted = bytearray(base64.urlsafe_b64decode(stored))
        corrupted[-1] ^= 1
        with pytest.raises(InvalidTag):
            connectors._decrypt_google_token(
                base64.urlsafe_b64encode(corrupted).decode("ascii"), "connector-test"
            )


def test_github_app_jwt_rs256_claims(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "test-app.pem"
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    config = SimpleNamespace(github_app_id="12345", github_app_private_key_path=str(key_path))
    with patch.object(connectors, "settings", return_value=config):
        encoded = connectors._github_jwt()
    claims = jwt.decode(encoded, key.public_key(), algorithms=["RS256"], options={
        "require": ["iat", "exp", "iss"],
    })
    assert jwt.get_unverified_header(encoded)["alg"] == "RS256"
    assert claims["iss"] == "12345"
    assert claims["exp"] - claims["iat"] == 600
