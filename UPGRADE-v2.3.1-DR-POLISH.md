# Engram v2.3.1 DR polish

Apply this source update to an existing v2.3/v2.3.1 deployment with the DR tables
already installed. VERSION remains `2.3.1`; the earlier release tag is not moved.
There are no API, database schema or environment variable changes.

## Deploy on Blackwall

The patch ZIP contains changed files under `memorybank/` plus a Git patch and
base-commit metadata. Back up your current source before overlaying it. Extract
the `memorybank/` contents into your existing checkout, preserving `.env`,
`secrets/`, backups and other runtime data. The full-source ZIP is an alternative
for a clean source directory. Neither ZIP contains credentials or runtime data.

From the deployment checkout:

```sh
docker compose build dr-monitor db-backup object-backup
docker compose up -d --force-recreate dr-monitor db-backup object-backup
docker compose logs --since 10m dr-monitor db-backup object-backup
```

Recreating the backup services starts a new backup cycle. Keep the existing
Blackwall-to-DarkMatter `DR_OFFSITE_REMOTE` and `secrets/rclone.conf` settings.
Replication remains `rclone copy` with checksum comparison; it does not delete
remote history. Only verified `.enc` artifacts are eligible. Plaintext, partial
files and symbolic links are excluded. Interrupted `.enc.partial` files may be
removed after confirming their writer is no longer running.

## Expected behavior

- The monitor checks the manual queue before its automatic scan and immediately
  after the scan. An operation already running is not interrupted; idle pickup
  still depends on `DR_MONITOR_INTERVAL_SECONDS` (300 seconds by default).
- A normal scan skips an unchanged, successfully verified artifact only while
  its local cache is less than 24 hours old and the database still records the
  same verified digest. Identity includes device, inode, size, mtime and ctime
  with subsecond precision. Failed checks are never cached. Cache hits do not
  advance `last_checked_at`, so that field remains evidence of a real check.
- Manual Verify/Scan bypasses the cache. Changed files and cache misses receive
  SHA-256, decryption and archive validation; changes during verification fail.
  Container recreation clears this temporary cache. Metadata caching is a
  performance optimization; daily forced rechecks still cover silent corruption
  that does not alter filesystem metadata.
- Manual restore/replicate uses the latest inventoried verified artifact of each
  type, revalidating as needed. If inventory is empty or its selected file is
  gone, only the newest timestamp-named candidate is verified. Newly published
  backups are added by the next scan; use manual Verify first to select them
  immediately when older verified inventory exists.
- Manual replication copies this selected pair. Automatic replication copies
  all inventoried verified history after confirming each cache entry or
  revalidating it. Invalid artifacts never enter a transfer manifest.
- `files_copied` and `bytes_copied` sum the final cumulative stats from each
  rclone invocation. An unchanged destination reports zero. Bytes reflect
  rclone transfer accounting (including retries), not total remote storage.
  Unsupported/malformed stats produce an explicit `stats unavailable` log;
  counters contain only available stats, retaining the existing numeric schema.
  Stats parsing follows [rclone JSON logging](https://rclone.org/docs/#use-json-log).
- UTC logs identify scan, verification/cache, queue, restore and replication
  events. Rclone error details remain in private, overwritten-per-run files
  `/tmp/memorybank-dr/rclone-{postgres,objects}.jsonl` inside the container;
  normal logs do not echo credentials or raw remote configuration.

## Verify the deployment

1. Trigger manual Verify and confirm full checks and completion in logs.
2. Let the next automatic scan run and confirm cache hits, with unchanged
   `last_checked_at` timestamps for unchanged artifacts.
3. Trigger manual Replicate and confirm queue processing begins without a scan;
   inspect its status, selected names and copy counters in the DR dashboard.
4. Trigger a restore test and confirm PostgreSQL, pgvector and object-reference
   results. Confirm DarkMatter receives only the expected encrypted artifacts.

## Local checks

On Linux as a non-root user, with PostgreSQL binaries, OpenSSL, rclone, jq,
ShellCheck and Python 3 installed:

```sh
shellcheck ops/dr-monitor/monitor.sh ops/db-backup/backup.sh ops/object-backup/backup.sh
python3 scripts/test-dr-monitor.py
sh scripts/check-repo-secrets.sh
```

The DR regression check creates a temporary PostgreSQL cluster using a private
Unix socket, encrypts real dump/tar backups and copies to a temporary local
rclone destination. It checks corruption and metadata changes, cache expiry,
forced verification, DB failure, queue order, transfer counts, encrypted-only
selection and restore cleanup. Its missing-pgvector case intentionally fails
the restore gate. It does not establish production pgvector restore success,
Docker image build success or live Blackwall/DarkMatter health.

## Rollback

Restore the previous source versions of the three `ops/` service directories
and rebuild/recreate those services with the commands above. No database
rollback is needed. Existing encrypted backups remain compatible.
