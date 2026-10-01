# Disaster Recovery

Engram v2.3 turns backup files into tested recovery evidence.

## What is covered

The DR system tracks:

- PostgreSQL encrypted backups
- MinIO/source-object encrypted backups
- SHA-256 hashes
- backup age
- retention deadline
- decrypt/integrity verification
- isolated PostgreSQL restore tests
- pgvector validation
- memory/document row counts
- object archive extraction
- restored-document object-reference checks
- backup filesystem capacity
- optional encrypted off-site replication

## Architecture

```text
db-backup ------------------+
                            |
                            v
                     ./backups/
                            |
object-backup ---------------+
                            |
                            v
                       dr-monitor
                   /       |       \
                  /        |        \
         verify archives  restore   rclone
                  |        test      copy
                  |         |         |
                  +---------+---------+
                            |
                            v
                       PostgreSQL
                       DR evidence
                            |
                            v
                  Disaster Recovery UI
```

The DR monitor never receives Docker socket access.

## Restore-test safety

The automated restore test:

1. decrypts the latest verified PostgreSQL archive
2. creates a disposable PostgreSQL database
3. restores the dump into that database
4. confirms the `vector` extension exists
5. counts memories and documents
6. decrypts and extracts the latest object backup
7. checks restored document `object_key` values against extracted files
8. records the result
9. drops the disposable database
10. removes temporary plaintext files

Production tables are never overwritten.

## Backup verification

A PostgreSQL archive is marked `verified` only when:

```text
decrypt succeeds
AND
pg_restore --list succeeds
```

An object archive is marked `verified` only when:

```text
decrypt succeeds
AND
tar archive listing succeeds
```

## Off-site replication

Off-site replication is optional and uses rclone.

Only encrypted `.enc` files are copied.

Configure:

```dotenv
DR_OFFSITE_REMOTE=b2:memorybank-backups
DR_OFFSITE_CONFIG_PATH=/run/secrets/rclone.conf
```

Place the rclone configuration at:

```text
secrets/rclone.conf
```

Protect it:

```bash
chmod 600 secrets/rclone.conf
```

Example targets supported by rclone include:

- Backblaze B2
- S3-compatible object stores
- SFTP
- Google Drive
- OneDrive
- another Linux server

The remote itself should be protected by least-privilege credentials.

## Dashboard

Open:

```text
/disaster-recovery
```

The dashboard shows:

- recovery score
- latest backup age
- backup integrity
- retention date
- restore-test result
- missing object references
- off-site copy status
- recent DR actions
- backup filesystem free space

## Manual actions

From the dashboard:

- Verify backups
- Run restore test
- Replicate off-site

The UI queues a request. The separate `dr-monitor` service performs the operation.

## Useful commands

Logs:

```bash
sudo docker compose logs -f dr-monitor
```

Recent backup evidence:

```bash
sudo docker compose exec db sh -lc \
'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT artifact_type,file_name,size_bytes,integrity_status,artifact_created_at
FROM dr_backup_artifacts
ORDER BY artifact_created_at DESC
LIMIT 20;
"'
```

Recent restore tests:

```bash
sudo docker compose exec db sh -lc \
'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT status,postgres_restore_ok,object_extract_ok,vector_extension_ok,
       memory_count,document_count,missing_object_refs,duration_seconds,completed_at
FROM dr_restore_tests
ORDER BY created_at DESC
LIMIT 10;
"'
```

## Interpretation

### Passed

The database restored successfully, pgvector exists, the object archive extracted, and all restored document object references were found.

### Warning

The database restored successfully, but the object side is incomplete or unavailable.

A warning can occur when the PostgreSQL and MinIO backups were created at slightly different times and recent documents exist in one snapshot but not the other.

### Failed

The PostgreSQL dump could not be decrypted/restored, or a required database validation failed.

Treat a failed restore test as an operational incident until understood.

## Plaintext handling

Plaintext dumps and extracted objects exist only temporarily inside the DR monitor container during verification.

They are removed after each run.

Off-site replication copies encrypted artifacts only.

## v2.3.1 recovery validation

A full off-site disaster-recovery exercise was completed on 2026-09-14 using
encrypted production backup artifacts replicated to a separate recovery host.

Results:

```text
PostgreSQL restore:         passed
pgvector validation:        passed
Object archive extraction:  passed
Memories restored:          672
Documents restored:         422
Object files restored:      422
Missing object references:  0
Restore duration:           17 seconds
```

Artifacts tested:

```text
memorybank-20260913T174550Z.dump.enc
memorybank-objects-20260913T174524Z.tar.gz.enc
```

The restore used a disposable PostgreSQL database and did not modify
the production database.

Temporary plaintext restore data was removed after the recovery test.

The complete recovery chain demonstrated was:

```text
Blackwall production
        |
        v
encrypted PostgreSQL + object backups
        |
        v
off-site replication
        |
        v
DarkMatter recovery host
        |
        v
decrypt backups
        |
        v
isolated PostgreSQL restore
        |
        v
pgvector validation
        |
        v
object archive extraction
        |
        v
document object-reference validation
        |
        v
PASS
```

The validation confirmed that all 422 restored documents with object references
had matching files in the restored object archive.

This provides tested recovery evidence for the complete Engram data path,
rather than relying only on the existence of backup files.
