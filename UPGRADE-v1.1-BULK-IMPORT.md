# Engram v1.1 — Bulk Folder + ZIP Import

This upgrade adds:

- multi-file bulk ingestion
- whole-folder selection
- recursive folder drag/drop where supported by the browser
- ZIP archive ingestion and safe server-side extraction
- folder-relative filenames
- SHA-256 duplicate detection
- batch result summaries
- ZIP traversal / symlink / encrypted-entry / expansion protections

## Upgrade an existing installation

Back up first:

```bash
cd /opt/memorybank/memorybank
sudo docker compose ps
```

Copy the updated project files over your existing project directory, keeping your existing `.env`.

Add these optional settings to `.env`:

```dotenv
BULK_MAX_FILES=1000
BULK_MAX_TOTAL_MB=500
ZIP_MAX_EXPANDED_MB=500
```

Then rebuild only the application pieces:

```bash
sudo docker compose build api worker web
sudo docker compose up -d --force-recreate api worker web gateway
```

Check:

```bash
sudo docker compose ps
sudo docker compose logs api --tail=50
sudo docker compose logs worker --tail=50
```

Open:

```text
https://YOUR-HOST/documents
```

The new **Bulk ingest** area will accept files, folders and ZIP archives.

No database migration is required for this release.
