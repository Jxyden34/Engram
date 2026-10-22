"""Owner-only issuer: python -m scripts.commercial_license --help (from backend)."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.licensing import AUDIENCE, ISSUER, PREFIX


def write_new(path: Path, data: bytes):
    # Exclusive creation avoids replacing an issuer key or a previously issued licence.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def issue(private_key: Ed25519PrivateKey, installation_id: str, customer: str, expires: date) -> str:
    installation_id = str(UUID(installation_id))
    customer = customer.strip()
    end = datetime.combine(expires + timedelta(days=1), time.min, timezone.utc)
    now = datetime.now(timezone.utc)
    if not 1 <= len(customer) <= 200 or end <= now:
        raise ValueError("Provide a customer (1–200 characters) and a current/future expiry date")
    return PREFIX + jwt.encode({
        "iss": ISSUER, "aud": AUDIENCE, "iat": int(now.timestamp()), "exp": int(end.timestamp()),
        "jti": str(uuid4()), "plan": "commercial", "customer": customer,
        "installation_id": installation_id,
    }, private_key, algorithm="EdDSA")


def main():
    parser = argparse.ArgumentParser(description="Issue offline commercial keys after payment and agreement")
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen", help="Generate an offline issuer keypair; never deploy the private key")
    keygen.add_argument("--private-key", type=Path, required=True)
    keygen.add_argument("--public-key", type=Path, required=True)
    mint = commands.add_parser("issue", help="Create a signed licence for one installation")
    mint.add_argument("--private-key", type=Path, required=True)
    mint.add_argument("--installation-id", required=True)
    mint.add_argument("--customer", required=True)
    mint.add_argument("--expires", type=date.fromisoformat, required=True, help="Last licensed day, inclusive in UTC")
    mint.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "keygen":
            if args.private_key.resolve() == args.public_key.resolve():
                raise ValueError("Private and public key paths must differ")
            if args.private_key.exists() or args.public_key.exists():
                raise ValueError("Key output paths must not already exist")
            private = Ed25519PrivateKey.generate()
            write_new(args.private_key, private.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            write_new(args.public_key, private.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
            print("Issuer keypair created. Keep the private key offline; deploy only the public key.")
        else:
            private = serialization.load_pem_private_key(args.private_key.read_bytes(), password=None)
            if not isinstance(private, Ed25519PrivateKey):
                raise ValueError("An Ed25519 issuer private key is required")
            token = issue(private, args.installation_id, args.customer, args.expires)
            write_new(args.output, (token + "\n").encode())
            print("Commercial licence written to the output file.")
    except (OSError, ValueError, OverflowError) as exc:
        parser.exit(1, f"Unable to issue licence: {exc}\n")


if __name__ == "__main__":
    main()
