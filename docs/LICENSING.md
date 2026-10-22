# Engram v3 editions

The v3 development branch offers two builds. Existing released versions retain their own licence notices.

| Build | Terms | Activation |
| --- | --- | --- |
| Community | Personal Self-Hosting License; personal and noncommercial use only | No key |
| Commercial | Separate commercial agreement | Signed key required for product access |

Build with `docker compose -f docker-compose.yml -f docker-compose.community.yml build`
or replace the final filename with `docker-compose.commercial.yml`.
Community images omit the proprietary implementation. Neither customer build contains the issuer CLI or private signing key.
Shared functionality remains available in Personal Community under its personal-use terms; the edition is set when building the image.
The frontend reads the edition from the backend rather than deciding access itself.

See [LICENSE](../LICENSE), [commercial terms](../LICENSE-COMMERCIAL), and
[owner setup](COMMERCIAL-LICENSING.md). Third-party licences still apply.
