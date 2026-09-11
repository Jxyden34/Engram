# MemoryBank Backup and Restore

MemoryBank contains sensitive personal knowledge and source documents.

A successful backup strategy must cover both:

```text
PostgreSQL
MinIO
```

A database-only backup is not a complete MemoryBank backup.

---

# PostgreSQL backup

## Create a custom-format dump

```bash
cd /opt/memorybank/memorybank

sudo docker compose exec db sh -lc   'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/memorybank.dump'
```

---

## Validate the archive

```bash
sudo docker compose exec db   pg_restore --list /tmp/memorybank.dump | head -30
```

If this fails, do not treat the backup as valid.

---

## Copy the backup to the host

```bash
sudo docker compose cp   db:/tmp/memorybank.dump   /home/jayden/memorybank.dump
```

Fix ownership if required:

```bash
sudo chown jayden:jayden /home/jayden/memorybank.dump
```

Verify:

```bash
ls -lh /home/jayden/memorybank.dump
```

---

# PostgreSQL restore

Restore into a clean test database first whenever possible.

A production restore should be treated as a deliberate recovery operation.

Example outline:

```bash
createdb memorybank_restore_test
pg_restore   --clean   --if-exists   --no-owner   -d memorybank_restore_test   memorybank.dump
```

When restoring inside Docker, use the database container and matching credentials.

---

# MinIO backup

MemoryBank source documents live in MinIO.

These include:

- uploaded files
- browser captures
- connector source documents
- imported exports

The object backup process should mirror the MinIO data into a local working directory and create an encrypted archive.

The backup workflow must create its temporary data directory before `mc mirror`.

Example structure:

```text
/tmp/object-backup/
└── data/
```

Encrypted backups should use strong encryption and a key stored separately from the backup.

---

# Full disaster recovery set

A complete recovery set should include:

```text
PostgreSQL dump
MinIO object backup
.env or secure copy of configuration
connector private keys
backup encryption credentials
deployment source code / Git repository
Cloudflare Tunnel configuration
```

Do not place production secrets inside the Git repository.

---

# Off-site copies

At least one backup copy should exist outside the MemoryBank host.

Possible targets:

- NAS
- secondary Linux server
- encrypted cloud object storage
- off-site server

An on-host backup does not protect against:

- disk failure
- theft
- filesystem corruption
- accidental host destruction

---

# Restore testing

A backup is not proven until a restore succeeds.

Recommended restore test:

1. create isolated test database
2. restore PostgreSQL
3. verify schema
4. verify memory counts
5. verify pgvector extension
6. verify important tables
7. restore or mount a copy of MinIO objects
8. verify document references
9. start isolated MemoryBank stack
10. confirm search and document retrieval work

---

# Useful verification queries

Database size:

```bash
sudo docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT pg_size_pretty(pg_database_size(current_database()));
"'
```

Memory count:

```bash
sudo docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT count(*) FROM memories;
"'
```

Document count:

```bash
sudo docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT count(*) FROM documents;
"'
```

---

# Retention

MemoryBank's existing backup design uses encrypted local backups and may retain approximately 14 days depending on configuration.

Retention should eventually include:

```text
daily local
daily off-host
weekly longer-term
monthly archive
```

---

# Recovery priorities

In a full-host disaster:

1. rebuild Linux host
2. install Docker
3. restore source repository
4. restore secrets and `.env`
5. restore PostgreSQL
6. restore MinIO data
7. pull Ollama models
8. start services
9. restore Cloudflare Tunnel
10. validate `/health`
11. validate search
12. validate source documents

---

# Security

Backups contain the same sensitive information as production.

Protect them accordingly.

Never:

- upload unencrypted backups publicly
- commit dumps to Git
- store encryption keys beside encrypted archives
- share backup files through unsecured channels
