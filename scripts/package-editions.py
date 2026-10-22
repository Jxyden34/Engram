#!/usr/bin/env python3
"""Create customer source bundles from committed Git files, never local secrets."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("backend/app/", "backend/scripts/", "web/", "db/", "gateway/", "ops/", "extensions/engram-capture/")
FILES = {"VERSION", "LICENSE", "LICENSE-COMMERCIAL", "SECURITY.md", ".env.example", "docker-compose.yml",
         "backend/Dockerfile", "backend/.dockerignore", "backend/requirements.txt",
         "docs/DEPLOYMENT.md", "docs/PROJECTS-AGENT.md", "docs/REFLECTION-BRIEFS.md",
         "docs/LICENSING.md", "docs/COMMERCIAL-LICENSING.md"}


def package(output: Path):
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(["git", "archive", "--format=zip", "HEAD"], cwd=ROOT)
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        version = archive.read("VERSION").decode().strip()
        if not version or any(c not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-" for c in version):
            raise ValueError("VERSION must be safe for a package filename")
        output.mkdir(parents=True, exist_ok=True)
        for edition, marker in [("personal", "community"), ("commercial", "commercial")]:
            target = output / f"engram-{version}-{edition}.zip"
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
                for name in archive.namelist():
                    if name.endswith("/") or not (name in FILES or name.startswith(DIRECTORIES)):
                        continue
                    if name == "backend/scripts/commercial_license.py":
                        continue
                    if edition == "personal" and (name.startswith("backend/app/commercial/") or name == "LICENSE-COMMERCIAL"):
                        continue
                    content = archive.read(name)
                    if name == "backend/Dockerfile":
                        content = content.replace(b"ARG ENGRAM_EDITION=community", f"ARG ENGRAM_EDITION={marker}".encode())
                    bundle.writestr(name, content)
                bundle.writestr("docker-compose.override.yml", archive.read(f"docker-compose.{marker}.yml"))
                bundle.writestr("backend/app/EDITION", marker)
                bundle.writestr("BUILD.json", json.dumps({"version": version, "edition": edition, "commit": commit}, indent=2) + "\n")
                terms = ("Free for personal, noncommercial use only. Business use requires the Commercial build and a paid key."
                         if edition == "personal" else "Business/commercial use requires an agreement and a valid paid licence key.")
                bundle.writestr("START-HERE.md", f"""# Engram {version} — {edition.title()}

{terms}

This is a source/build package, not a prebuilt Docker image. Install Docker Engine
and the Compose plugin on a Linux host. Read docs/DEPLOYMENT.md for environment,
storage and network setup. Existing installations must apply migrations through 014.
Use docs/PROJECTS-AGENT.md for the project migrations and docs/REFLECTION-BRIEFS.md
for migration 013. Apply db/migrations/014_commercial_license.sql with psql before
starting a v3 API on an existing database. New databases apply these on first boot.

1. Copy `.env.example` to `.env` and configure independent secrets and your domain.
2. Run `docker compose build`. The included override selects {edition.title()}.
3. Run `docker compose up -d` and follow the deployment guide to create your admin.
""" + ("\nCommercial: install the issuer PUBLIC key at `secrets/commercial-license-public.pem`,\nset `COMMERCIAL_LICENSE_PURCHASE_URL`, then open `/licence` to activate your key.\n" if edition == "commercial" else "\nPersonal: no licence key or activation is required.\n") + "\nThe owner dashboard, issuer CLI, SMTP credentials and private signing key are not included.\n")
            with zipfile.ZipFile(target) as bundle:
                names = set(bundle.namelist())
                assert not any(name.startswith("backend/owner/") for name in names)
                assert "backend/scripts/commercial_license.py" not in names
                assert ("backend/app/commercial/licensing.py" in names) == (edition == "commercial")
                assert bundle.read("backend/app/EDITION").decode() == marker
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
            print(f"Created {target.name} ({commit[:8]})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "editions")
    package(parser.parse_args().output)
