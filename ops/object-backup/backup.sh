#!/bin/sh
set -eu
umask 077
mkdir -p /backups /tmp/object-backup
while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  rm -rf /tmp/object-backup/*
  mkdir -p /tmp/object-backup/data
  mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
  mc mirror --overwrite local/"$MINIO_BUCKET" /tmp/object-backup/data
  tar -C /tmp/object-backup -czf "/tmp/memorybank-objects-${stamp}.tar.gz" data
  openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
    -in "/tmp/memorybank-objects-${stamp}.tar.gz" \
    -out "/backups/memorybank-objects-${stamp}.tar.gz.enc.partial" \
    -pass env:BACKUP_ENCRYPTION_PASSWORD
  mv "/backups/memorybank-objects-${stamp}.tar.gz.enc.partial" \
    "/backups/memorybank-objects-${stamp}.tar.gz.enc"
  rm -f "/tmp/memorybank-objects-${stamp}.tar.gz"
  find /backups -type f -name '*.enc' -mtime "+${BACKUP_RETENTION_DAYS:-14}" -delete
  sleep 86400
done
