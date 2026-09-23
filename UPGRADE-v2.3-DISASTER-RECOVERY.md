# Engram v2.3 — Disaster Recovery

v2.3 adds tested recovery evidence rather than relying on backup-file existence alone.

## Included

- DR dashboard
- backup artifact inventory
- SHA-256 hashes
- encrypted archive verification
- backup freshness monitoring
- retention visibility
- isolated PostgreSQL restore tests
- pgvector verification
- MinIO archive extraction tests
- document object-reference checks
- backup filesystem capacity checks
- optional encrypted off-site replication via rclone
- manual verify / restore-test / replicate actions

## 1. Back up the database

```bash
cd /opt/memorybank/memorybank

sudo docker compose exec db sh -lc \
  'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/memorybank-pre-v2.3.dump'

sudo docker compose exec db \
  pg_restore --list /tmp/memorybank-pre-v2.3.dump | head -30
```

## 2. Pause background ingestion

```bash
sudo docker compose stop worker connector-scheduler
```

## 3. Extract the patch

```bash
cd /opt/memorybank

sudo unzip -o \
  /home/jayden/memorybank-v2.3-disaster-recovery-patch.zip \
  -d /opt/memorybank

cd /opt/memorybank/memorybank
```

## 4. Apply migration 007

```bash
sudo docker compose exec -T db sh -lc \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/migrations/007_disaster_recovery.sql
```

## 5. Add DR settings

Add to `.env`:

```dotenv
DR_MONITOR_INTERVAL_SECONDS=300
DR_MAX_BACKUP_AGE_HOURS=36
DR_RESTORE_TEST_INTERVAL_HOURS=24
DR_RESTORE_TEST_MAX_AGE_HOURS=36
DR_RESTORE_TEST_ENABLED=true
DR_MIN_BACKUP_FREE_GB=10

DR_OFFSITE_REMOTE=
DR_OFFSITE_CONFIG_PATH=/run/secrets/rclone.conf
DR_OFFSITE_INTERVAL_HOURS=6
```

Leave `DR_OFFSITE_REMOTE` blank until an off-host target is configured.

## 6. Rebuild

```bash
sudo docker compose build --no-cache \
  api worker web connector-scheduler dr-monitor
```

## 7. Start v2.3

```bash
sudo docker compose up -d \
  --force-recreate \
  api worker web gateway connector-scheduler dr-monitor
```

The existing backup services should also be running:

```bash
sudo docker compose up -d db-backup object-backup
```

## 8. Verify

```bash
sudo docker compose ps
```

You should now have:

```text
dr-monitor
```

Watch its first scan:

```bash
sudo docker compose logs -f dr-monitor
```

## 9. Open the dashboard

Hard refresh:

```text
Ctrl + F5
```

Open:

```text
/disaster-recovery
```

The first restore test may take longer than a normal status refresh because it performs a real restore into a temporary database.

## 10. Optional off-site replication

Create an rclone config on Blackwall and place it at:

```text
/opt/memorybank/memorybank/secrets/rclone.conf
```

Protect it:

```bash
chmod 600 secrets/rclone.conf
```

Then set:

```dotenv
DR_OFFSITE_REMOTE=YOUR_RCLONE_REMOTE:memorybank-backups
```

Recreate the monitor:

```bash
sudo docker compose up -d --force-recreate dr-monitor
```

Only encrypted backup artifacts are copied off-host.

## Rollback

Migration 007 is additive. Existing memories, documents and backup services are not replaced.

To roll back the application layer, restore the v2.2 code and stop:

```bash
sudo docker compose stop dr-monitor
```
