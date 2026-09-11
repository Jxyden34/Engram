# Contributing

## Development flow

1. Create a branch from `main`.
2. Make focused changes.
3. Do not commit `.env`, production exports, backups, tokens or personal data.
4. Run the local checks.
5. Open a pull request describing the change and any required migration.

## Local checks

Backend syntax:

```bash
python -m compileall -q backend/app backend/scripts
```

Frontend:

```bash
cd web
npm install
npm run build
```

Docker:

```bash
cp .env.example .env
docker compose config >/dev/null
docker compose build api worker web
```

Remove the temporary `.env` afterwards if it contains only example values.

## Database changes

Never edit an already-deployed migration.

Create a new numbered migration:

```text
db/migrations/005_example.sql
```

Prefer additive and idempotent changes where practical.

## Pull requests

Document:

- what changed
- why
- database migrations
- environment changes
- deployment/restart requirements
- rollback notes
