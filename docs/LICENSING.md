# Engram v3.7 editions

The v3.7 development branch offers two builds. Existing released versions retain their own licence notices.

| Build | Terms | Activation |
| --- | --- | --- |
| Personal (Community) | Personal Self-Hosting License; personal and noncommercial use only | No key |
| Commercial | Separate commercial agreement | Signed key required for product access |

Build with `docker compose -f docker-compose.yml -f docker-compose.community.yml build`
or replace the final filename with `docker-compose.commercial.yml`.
Community images omit the proprietary implementation. Neither customer build contains the issuer CLI or private signing key.
Shared functionality remains available in Personal Community under its personal-use terms; the edition is set when building the image.
The frontend reads the edition from the backend rather than deciding access itself.

## Customer downloads

CI produces separate `engram-<version>-personal.zip` and `engram-<version>-commercial.zip`
source/build packages with SHA-256 checksums in its **engram-customer-editions** artifact.
They are development artifacts, not stable releases or prebuilt Docker images.
Each has a `START-HERE.md`, a build identity in `BUILD.json`, and an automatic Compose
override so `docker compose build` selects the correct edition. The Commercial package
also defaults direct backend Docker builds to Commercial.

Personal packages omit commercial implementation code. Both packages omit the owner
service, issuer CLI and runtime secrets. Existing memories, projects and app features
are preserved; the split changes packaging and activation, not project data.

Maintainers can generate them from the current **committed** checkout with
`python scripts/package-editions.py --output dist/editions`. Uncommitted files are excluded.

See [LICENSE](../LICENSE), [commercial terms](../LICENSE-COMMERCIAL), and
[owner setup](COMMERCIAL-LICENSING.md). Third-party licences still apply.
