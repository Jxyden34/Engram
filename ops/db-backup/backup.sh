#!/bin/sh
set -eu
mkdir -p /backups
while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  plain="/backups/memorybank-${stamp}.dump"
  encrypted="${plain}.enc"
  pg_dump -Fc -f "$plain"
  openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
    -in "$plain" -out "$encrypted" -pass env:BACKUP_ENCRYPTION_PASSWORD
  rm -f "$plain"
  find /backups -type f -name '*.enc' -mtime "+${BACKUP_RETENTION_DAYS:-14}" -delete
  sleep 86400
done
