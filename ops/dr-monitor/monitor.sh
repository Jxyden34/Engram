#!/bin/sh
set -eu

: "${PGHOST:=db}"
: "${PGPORT:=5432}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${BACKUP_ENCRYPTION_PASSWORD:?BACKUP_ENCRYPTION_PASSWORD is required}"
: "${BACKUP_RETENTION_DAYS:=14}"
: "${DR_MONITOR_INTERVAL_SECONDS:=300}"
: "${DR_MAX_BACKUP_AGE_HOURS:=36}"
: "${DR_RESTORE_TEST_INTERVAL_HOURS:=24}"
: "${DR_RESTORE_TEST_ENABLED:=true}"
: "${DR_OFFSITE_INTERVAL_HOURS:=6}"
: "${DR_OFFSITE_CONFIG_PATH:=/run/secrets/rclone.conf}"
: "${DR_OFFSITE_REMOTE:=}"
: "${DR_MIN_BACKUP_FREE_GB:=10}"

export PGPASSWORD
WORKDIR="/tmp/memorybank-dr"
mkdir -p "$WORKDIR"

psql_main() {
  psql -X -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" "$@"
}

sql_escape() {
  printf "%s" "$1" | sed "s/'/''/g"
}

set_status() {
  key="$(sql_escape "$1")"
  status="$(sql_escape "$2")"
  details="$3"
  psql_main -qAtc "
    INSERT INTO dr_status(key,status,details,checked_at)
    VALUES ('$key','$status','$details'::jsonb,now())
    ON CONFLICT (key)
    DO UPDATE SET status=EXCLUDED.status,
                  details=EXCLUDED.details,
                  checked_at=now();
  "
}

artifact_upsert() {
  type="$1"
  file="$2"
  integrity="$3"
  err="${4:-}"

  name="$(basename "$file")"
  size="$(stat -c '%s' "$file" 2>/dev/null || echo 0)"
  mtime="$(stat -c '%Y' "$file" 2>/dev/null || date +%s)"
  digest="$(sha256sum "$file" | awk '{print $1}')"
  err_sql="$(sql_escape "$err")"
  path_sql="$(sql_escape "$file")"
  name_sql="$(sql_escape "$name")"

  psql_main -qAtc "
    INSERT INTO dr_backup_artifacts(
      artifact_type,file_name,file_path,size_bytes,sha256,encrypted,
      integrity_status,integrity_error,artifact_created_at,retention_until,
      last_checked_at
    )
    VALUES (
      '$type','$name_sql','$path_sql',$size,'$digest',true,
      '$integrity',NULLIF('$err_sql',''),to_timestamp($mtime),
      to_timestamp($mtime) + interval '${BACKUP_RETENTION_DAYS} days',
      now()
    )
    ON CONFLICT (artifact_type,file_name)
    DO UPDATE SET
      file_path=EXCLUDED.file_path,
      size_bytes=EXCLUDED.size_bytes,
      sha256=EXCLUDED.sha256,
      encrypted=true,
      integrity_status=EXCLUDED.integrity_status,
      integrity_error=EXCLUDED.integrity_error,
      artifact_created_at=EXCLUDED.artifact_created_at,
      retention_until=EXCLUDED.retention_until,
      last_checked_at=now();
  "
}

verify_postgres_artifact() {
  file="$1"
  tmp="$WORKDIR/verify.dump"
  rm -f "$tmp"
  if openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
      -in "$file" -out "$tmp" -pass env:BACKUP_ENCRYPTION_PASSWORD >/dev/null 2>&1 \
     && pg_restore --list "$tmp" >/dev/null 2>&1; then
    artifact_upsert postgres "$file" verified ""
  else
    artifact_upsert postgres "$file" failed "decrypt or pg_restore archive verification failed"
  fi
  rm -f "$tmp"
}

verify_object_artifact() {
  file="$1"
  tmp="$WORKDIR/verify-objects.tar.gz"
  rm -f "$tmp"
  if openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
      -in "$file" -out "$tmp" -pass env:BACKUP_ENCRYPTION_PASSWORD >/dev/null 2>&1 \
     && tar -tzf "$tmp" >/dev/null 2>&1; then
    artifact_upsert objects "$file" verified ""
  else
    artifact_upsert objects "$file" failed "decrypt or tar archive verification failed"
  fi
  rm -f "$tmp"
}

scan_backups() {
  mkdir -p /backups/postgres /backups/objects

  for file in /backups/postgres/*.enc; do
    [ -f "$file" ] || continue
    verify_postgres_artifact "$file"
  done

  for file in /backups/objects/*.enc; do
    [ -f "$file" ] || continue
    verify_object_artifact "$file"
  done

  # Remove DB inventory rows for artifacts that no longer exist after retention cleanup.
  psql_main -qAtc "SELECT artifact_type || '|' || id || '|' || file_path FROM dr_backup_artifacts;" |
  while IFS='|' read -r type id path; do
    if [ ! -f "$path" ]; then
      psql_main -qAtc "DELETE FROM dr_backup_artifacts WHERE id='$id';" >/dev/null
    fi
  done

  free_kb="$(df -Pk /backups | awk 'NR==2 {print $4}')"
  total_kb="$(df -Pk /backups | awk 'NR==2 {print $2}')"
  free_gb="$(awk -v kb="$free_kb" 'BEGIN { printf "%.2f", kb/1024/1024 }')"
  total_gb="$(awk -v kb="$total_kb" 'BEGIN { printf "%.2f", kb/1024/1024 }')"

  disk_status="healthy"
  if awk -v free="$free_gb" -v min="$DR_MIN_BACKUP_FREE_GB" 'BEGIN { exit !(free < min) }'; then
    disk_status="warning"
  fi

  set_status backup_disk "$disk_status" \
    "{\"free_gb\":$free_gb,\"total_gb\":$total_gb,\"minimum_free_gb\":$DR_MIN_BACKUP_FREE_GB}"

  set_status monitor healthy \
    "{\"last_scan\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"interval_seconds\":$DR_MONITOR_INTERVAL_SECONDS}"
}

latest_verified_path() {
  type="$1"
  psql_main -qAtc "
    SELECT file_path
    FROM dr_backup_artifacts
    WHERE artifact_type='$type' AND integrity_status='verified'
    ORDER BY artifact_created_at DESC NULLS LAST
    LIMIT 1;
  "
}

latest_verified_id() {
  type="$1"
  psql_main -qAtc "
    SELECT id
    FROM dr_backup_artifacts
    WHERE artifact_type='$type' AND integrity_status='verified'
    ORDER BY artifact_created_at DESC NULLS LAST
    LIMIT 1;
  "
}

run_restore_test() {
  requested_by="${1:-system:auto}"
  pg_file="$(latest_verified_path postgres)"
  obj_file="$(latest_verified_path objects)"
  pg_id="$(latest_verified_id postgres)"
  obj_id="$(latest_verified_id objects)"

  if [ -z "$pg_file" ] || [ ! -f "$pg_file" ]; then
    return 1
  fi

  test_id="$(psql_main -qAtc "
    INSERT INTO dr_restore_tests(
      status,requested_by,postgres_artifact_id,object_artifact_id,started_at
    )
    VALUES (
      'processing','$(sql_escape "$requested_by")',
      NULLIF('$pg_id','')::uuid,NULLIF('$obj_id','')::uuid,now()
    )
    RETURNING id;
  ")"

  started="$(date +%s)"
  tmp_dump="$WORKDIR/restore.dump"
  tmp_tar="$WORKDIR/objects.tar.gz"
  extract_dir="$WORKDIR/objects"
  test_db="memorybank_dr_$(date +%s)_$$"
  pg_ok=false
  obj_ok=false
  vector_ok=false
  memory_count=0
  document_count=0
  object_count=0
  missing_refs=0
  final_status=failed
  error=""

  cleanup_restore() {
    dropdb -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" --if-exists "$test_db" >/dev/null 2>&1 || true
    rm -rf "$tmp_dump" "$tmp_tar" "$extract_dir"
  }
  trap cleanup_restore EXIT INT TERM

  rm -rf "$tmp_dump" "$tmp_tar" "$extract_dir"
  mkdir -p "$extract_dir"

  if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
      -in "$pg_file" -out "$tmp_dump" -pass env:BACKUP_ENCRYPTION_PASSWORD >/dev/null 2>&1; then
    error="PostgreSQL backup decryption failed"
  elif ! createdb -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" "$test_db" >/dev/null 2>&1; then
    error="Could not create isolated restore-test database"
  elif ! pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$test_db" \
      --no-owner --no-privileges --exit-on-error "$tmp_dump" >/dev/null 2>&1; then
    error="pg_restore failed in isolated restore-test database"
  else
    pg_ok=true

    vector_count="$(psql -X -qAt -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$test_db" \
      -c "SELECT count(*) FROM pg_extension WHERE extname='vector';" 2>/dev/null || echo 0)"
    [ "$vector_count" = "1" ] && vector_ok=true

    memory_count="$(psql -X -qAt -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$test_db" \
      -c "SELECT count(*) FROM memories;" 2>/dev/null || echo 0)"
    document_count="$(psql -X -qAt -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$test_db" \
      -c "SELECT count(*) FROM documents;" 2>/dev/null || echo 0)"

    if [ -n "$obj_file" ] && [ -f "$obj_file" ]; then
      if openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
          -in "$obj_file" -out "$tmp_tar" -pass env:BACKUP_ENCRYPTION_PASSWORD >/dev/null 2>&1 \
         && tar -xzf "$tmp_tar" -C "$extract_dir" >/dev/null 2>&1; then
        obj_ok=true
        object_count="$(find "$extract_dir/data" -type f 2>/dev/null | wc -l | tr -d ' ')"

        psql -X -qAt -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$test_db" \
          -c "SELECT object_key FROM documents WHERE object_key IS NOT NULL ORDER BY object_key;" 2>/dev/null |
        while IFS= read -r key; do
          [ -n "$key" ] || continue
          if [ ! -f "$extract_dir/data/$key" ]; then
            echo 1 >> "$WORKDIR/missing.$test_id"
          fi
        done
        if [ -f "$WORKDIR/missing.$test_id" ]; then
          missing_refs="$(wc -l < "$WORKDIR/missing.$test_id" | tr -d ' ')"
          rm -f "$WORKDIR/missing.$test_id"
        fi
      fi
    fi

    if [ "$pg_ok" = true ] && [ "$vector_ok" = true ]; then
      if [ "$obj_ok" = true ] && [ "$missing_refs" -eq 0 ]; then
        final_status=passed
      elif [ -z "$obj_file" ]; then
        final_status=warning
        error="PostgreSQL restored successfully, but no verified object backup was available"
      elif [ "$obj_ok" != true ]; then
        final_status=warning
        error="PostgreSQL restored successfully, but object archive extraction failed"
      else
        final_status=warning
        error="$missing_refs restored document object reference(s) were absent from the latest object backup"
      fi
    else
      final_status=failed
      error="Restore completed but required vector extension validation failed"
    fi
  fi

  duration="$(( $(date +%s) - started ))"
  db_size="$(psql_main -qAtc "SELECT pg_database_size(current_database());" 2>/dev/null || echo 0)"
  err_sql="$(sql_escape "$error")"

  psql_main -qAtc "
    UPDATE dr_restore_tests
    SET status='$final_status',
        postgres_restore_ok=$pg_ok,
        object_extract_ok=$obj_ok,
        vector_extension_ok=$vector_ok,
        memory_count=$memory_count,
        document_count=$document_count,
        object_file_count=$object_count,
        missing_object_refs=$missing_refs,
        database_size_bytes=$db_size,
        duration_seconds=$duration,
        error_message=NULLIF('$err_sql',''),
        details=jsonb_build_object(
          'test_database','$test_db',
          'postgres_artifact','$(sql_escape "$(basename "$pg_file")")',
          'object_artifact','$(sql_escape "$(basename "${obj_file:-}")")'
        ),
        completed_at=now()
    WHERE id='$test_id';
  "

  cleanup_restore
  trap - EXIT INT TERM

  [ "$final_status" != failed ]
}

run_replication() {
  requested_by="${1:-system:auto}"

  if [ -z "$DR_OFFSITE_REMOTE" ]; then
    psql_main -qAtc "
      INSERT INTO dr_replication_runs(
        status,requested_by,target,error_message,started_at,completed_at
      )
      VALUES (
        'disabled','$(sql_escape "$requested_by")',NULL,
        'DR_OFFSITE_REMOTE is not configured',now(),now()
      );
    "
    return 0
  fi

  if [ ! -f "$DR_OFFSITE_CONFIG_PATH" ]; then
    psql_main -qAtc "
      INSERT INTO dr_replication_runs(
        status,requested_by,target,error_message,started_at,completed_at
      )
      VALUES (
        'failed','$(sql_escape "$requested_by")','$(sql_escape "$DR_OFFSITE_REMOTE")',
        'rclone configuration file is missing',now(),now()
      );
    "
    return 1
  fi

  pg_file="$(latest_verified_path postgres)"
  obj_file="$(latest_verified_path objects)"
  pg_name="$(basename "${pg_file:-}")"
  obj_name="$(basename "${obj_file:-}")"

  run_id="$(psql_main -qAtc "
    INSERT INTO dr_replication_runs(status,requested_by,target,postgres_file_name,object_file_name,started_at)
    VALUES (
      'processing','$(sql_escape "$requested_by")','$(sql_escape "$DR_OFFSITE_REMOTE")',
      '$(sql_escape "$pg_name")','$(sql_escape "$obj_name")',now()
    )
    RETURNING id;
  ")"

  started="$(date +%s)"
  status=passed
  error=""
  pg_remote=false
  obj_remote=false

  if ! rclone copy /backups/postgres "${DR_OFFSITE_REMOTE%/}/postgres" \
      --config "$DR_OFFSITE_CONFIG_PATH" --include '*.enc' --checksum >/dev/null 2>&1; then
    status=failed
    error="PostgreSQL off-site replication failed"
  fi

  if [ "$status" != failed ] && ! rclone copy /backups/objects "${DR_OFFSITE_REMOTE%/}/objects" \
      --config "$DR_OFFSITE_CONFIG_PATH" --include '*.enc' --checksum >/dev/null 2>&1; then
    status=failed
    error="Object off-site replication failed"
  fi

  if [ "$status" != failed ] && [ -n "$pg_name" ]; then
    if rclone lsf "${DR_OFFSITE_REMOTE%/}/postgres/$pg_name" \
        --config "$DR_OFFSITE_CONFIG_PATH" >/dev/null 2>&1; then
      pg_remote=true
    else
      status=warning
      error="Replication completed, but latest PostgreSQL artifact could not be verified remotely"
    fi
  fi

  if [ "$status" != failed ] && [ -n "$obj_name" ]; then
    if rclone lsf "${DR_OFFSITE_REMOTE%/}/objects/$obj_name" \
        --config "$DR_OFFSITE_CONFIG_PATH" >/dev/null 2>&1; then
      obj_remote=true
    else
      status=warning
      error="Replication completed, but latest object artifact could not be verified remotely"
    fi
  fi

  duration="$(( $(date +%s) - started ))"
  err_sql="$(sql_escape "$error")"

  psql_main -qAtc "
    UPDATE dr_replication_runs
    SET status='$status',
        postgres_present_remote=$pg_remote,
        object_present_remote=$obj_remote,
        duration_seconds=$duration,
        error_message=NULLIF('$err_sql',''),
        completed_at=now()
    WHERE id='$run_id';
  "

  [ "$status" != failed ]
}

process_requests() {
  psql_main -qAtc "
    SELECT id || '|' || action || '|' || replace(requested_by,'|','')
    FROM dr_requests
    WHERE status='queued'
    ORDER BY created_at
    LIMIT 20;
  " |
  while IFS='|' read -r request_id action requested_by; do
    [ -n "$request_id" ] || continue
    psql_main -qAtc "
      UPDATE dr_requests
      SET status='processing',started_at=now()
      WHERE id='$request_id' AND status='queued';
    "

    ok=true
    case "$action" in
      scan)
        scan_backups || ok=false
        ;;
      restore_test)
        scan_backups || true
        run_restore_test "$requested_by" || ok=false
        ;;
      replicate)
        scan_backups || true
        run_replication "$requested_by" || ok=false
        ;;
      *)
        ok=false
        ;;
    esac

    if [ "$ok" = true ]; then
      psql_main -qAtc "
        UPDATE dr_requests
        SET status='completed',completed_at=now()
        WHERE id='$request_id';
      "
    else
      psql_main -qAtc "
        UPDATE dr_requests
        SET status='failed',error_message='DR action failed; inspect restore/replication records',
            completed_at=now()
        WHERE id='$request_id';
      "
    fi
  done
}

auto_restore_due() {
  [ "$DR_RESTORE_TEST_ENABLED" = "true" ] || return 1
  last_epoch="$(psql_main -qAtc "
    SELECT coalesce(extract(epoch FROM max(completed_at))::bigint,0)
    FROM dr_restore_tests
    WHERE status IN ('passed','warning','failed');
  ")"
  now="$(date +%s)"
  due="$(( DR_RESTORE_TEST_INTERVAL_HOURS * 3600 ))"
  [ "$(( now - last_epoch ))" -ge "$due" ]
}

auto_replication_due() {
  [ -n "$DR_OFFSITE_REMOTE" ] || return 1
  last_epoch="$(psql_main -qAtc "
    SELECT coalesce(extract(epoch FROM max(completed_at))::bigint,0)
    FROM dr_replication_runs
    WHERE status IN ('passed','warning','failed');
  ")"
  now="$(date +%s)"
  due="$(( DR_OFFSITE_INTERVAL_HOURS * 3600 ))"
  [ "$(( now - last_epoch ))" -ge "$due" ]
}

echo "MemoryBank DR monitor starting"

while true; do
  scan_backups || true
  process_requests || true

  if auto_restore_due; then
    run_restore_test "system:auto" || true
  fi

  if auto_replication_due; then
    run_replication "system:auto" || true
  fi

  sleep "$DR_MONITOR_INTERVAL_SECONDS"
done
