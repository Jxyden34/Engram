# MemoryBank Upgrading

Use this procedure when upgrading an existing MemoryBank deployment.

The goal is simple:

```text
backup
pause ingestion
migrate
rebuild
verify
resume
```

---

## 1. Enter the project

```bash
cd /opt/memorybank/memorybank
```

---

## 2. Back up PostgreSQL

Create a PostgreSQL custom-format backup:

```bash
sudo docker compose exec db sh -lc   'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/memorybank-pre-upgrade.dump'
```

Validate that the archive is readable:

```bash
sudo docker compose exec db   pg_restore --list /tmp/memorybank-pre-upgrade.dump | head -30
```

Copy it out of the container:

```bash
sudo docker compose cp   db:/tmp/memorybank-pre-upgrade.dump   /home/jayden/memorybank-pre-upgrade.dump
```

Verify:

```bash
ls -lh /home/jayden/memorybank-pre-upgrade.dump
```

Do not continue if the backup cannot be validated.

---

## 3. Pause background ingestion

```bash
sudo docker compose stop worker connector-scheduler 2>/dev/null || true
```

This prevents document and connector jobs from changing data during schema migration.

---

## 4. Update the source

If using Git:

```bash
git pull
```

If using an upgrade patch:

```bash
cd /opt/memorybank

sudo unzip -o   /home/jayden/memorybank-UPGRADE-PATCH.zip   -d /opt/memorybank
```

Return to the project:

```bash
cd /opt/memorybank/memorybank
```

---

## 5. Apply migrations

Migrations live under:

```text
db/migrations/
```

Apply only migrations that have not previously been applied.

Example:

```bash
sudo docker compose exec -T db sh -lc   'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'   < db/migrations/005_ingestion_mesh.sql
```

`ON_ERROR_STOP=1` ensures the command fails immediately if PostgreSQL encounters a migration error.

---

## 6. Rebuild services

For application changes:

```bash
sudo docker compose build --no-cache api worker web connector-scheduler
```

---

## 7. Recreate services

```bash
sudo docker compose up -d   --force-recreate   api worker web gateway connector-scheduler
```

---

## 8. Check container status

```bash
sudo docker compose ps
```

All required services should be running.

---

## 9. Check logs

```bash
sudo docker compose logs api --tail=100
sudo docker compose logs worker --tail=100
sudo docker compose logs web --tail=100
sudo docker compose logs connector-scheduler --tail=100
```

---

## 10. Health check

```bash
curl http://127.0.0.1:8080/health
```

---

## 11. Verify routes

Example:

```bash
sudo docker compose exec api python -c 'from app.main import app; print([r.path for r in app.routes])'
```

Use this when confirming that a newly-added API area was loaded.

---

## 12. Resume ingestion

If the worker was not recreated automatically:

```bash
sudo docker compose up -d worker connector-scheduler
```

---

# Current migration history

Typical MemoryBank migrations include:

```text
001  initial schema
002  ChatGPT importer
003  document Memory Inbox
004  Knowledge Core
005  Ingestion Mesh
```

Never modify an already-deployed migration file.

Create a new numbered migration instead.

---

# Rollback strategy

If a deployment fails before schema migration:

```bash
git checkout <previous-version>
sudo docker compose build
sudo docker compose up -d
```

If the database migration itself must be rolled back, restore the validated pre-upgrade backup into a clean database.

Do not blindly overwrite the only production copy without first preserving the failed state for inspection.

---

# Safe upgrade rules

1. Always back up before schema changes.
2. Validate the backup.
3. Pause ingestion during migration.
4. Use `ON_ERROR_STOP=1`.
5. Never edit old migrations.
6. Rebuild only after migrations succeed.
7. Check logs before declaring success.
8. Keep secrets outside Git.
