#!/usr/bin/env python3
"""Isolated Linux DR regression check. Requires PostgreSQL, rclone, jq, OpenSSL.

Run as a non-root user: python3 scripts/test-dr-monitor.py
Uses a temporary cluster/socket and local remote; never uses deployment credentials.
"""
import getpass
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    pg_config = shutil.which("pg_config")
    if pg_config:
        pg_bin = subprocess.check_output([pg_config, "--bindir"], text=True).strip()
    else:
        pg_bin = str(sorted(Path("/usr/lib/postgresql").glob("*/bin"))[-1])
    with tempfile.TemporaryDirectory(prefix="memorybank-dr-test-") as directory:
        root = Path(directory)
        env = dict(os.environ, PATH=pg_bin + os.pathsep + os.environ["PATH"],
                   PGHOST=str(root), PGPORT="5432", PGDATABASE="postgres",
                   PGUSER=getpass.getuser(), PGPASSWORD="isolated-test-only",
                   BACKUP_ENCRYPTION_PASSWORD="isolated-test-only",
                   DR_OFFSITE_REMOTE=str(root / "remote"),
                   DR_OFFSITE_CONFIG_PATH=str(root / "rclone.conf"))
        (root / "rclone.conf").touch()

        def run(*args, input=None, check=True):
            return subprocess.run(args, input=input, env=env, text=True,
                                  capture_output=True, check=check)

        def sql(query):
            return run("psql", "-XqAt", "-v", "ON_ERROR_STOP=1", "-c", query).stdout.strip()

        source = (ROOT / "ops/dr-monitor/monitor.sh").read_text()
        functions, loop = source.split('log "starting version=2.4.0"', 1)
        functions = functions.replace('WORKDIR="/tmp/memorybank-dr"',
                                      f'WORKDIR="{root}/work"')
        functions = functions.replace("/backups", str(root / "backups"))

        def shell(command, success=True, prefix=""):
            result = run("sh", "-s", input=functions + "\n" + prefix + "\n" + command,
                         check=False)
            assert (result.returncode == 0) == success, result.stdout + result.stderr
            return result

        run("initdb", "-D", str(root / "pg"), "-A", "trust", "--no-locale")
        run("pg_ctl", "-D", str(root / "pg"), "-l", str(root / "pg.log"),
            "-o", f"-k {root} -c listen_addresses=''", "-w", "start")
        try:
            schema = (ROOT / "db/init.sql").read_text()
            sql(schema[schema.index("CREATE TABLE IF NOT EXISTS dr_backup_artifacts"):])
            sql("CREATE TABLE memories(id integer); CREATE TABLE documents(object_key text);")
            for kind in ("postgres", "objects"):
                (root / "backups" / kind).mkdir(parents=True)
            dump = root / "backup.dump"
            run("pg_dump", "-Fc", "-f", str(dump))
            (root / "data").mkdir()
            (root / "data/document.txt").write_text("test document")
            archive = root / "objects.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(root / "data", arcname="data")
            pg = root / "backups/postgres/memorybank-20260918T000000Z.dump.enc"
            obj = root / "backups/objects/memorybank-objects-20260918T000000Z.tar.gz.enc"
            for plain, encrypted in ((dump, pg), (archive, obj)):
                run("openssl", "enc", "-aes-256-cbc", "-salt", "-pbkdf2", "-iter", "200000",
                    "-in", str(plain), "-out", str(encrypted),
                    "-pass", "env:BACKUP_ENCRYPTION_PASSWORD")

            # Cold manual replication discovers only its selected backups; no scan.
            result = shell("run_replication test:manual selected")
            assert "scan start" not in result.stderr
            expected_bytes = pg.stat().st_size + obj.stat().st_size
            assert sql("SELECT files_copied || '|' || bytes_copied FROM dr_replication_runs "
                       "ORDER BY created_at DESC LIMIT 1") == f"2|{expected_bytes}"
            assert sql("SELECT status || '|' || postgres_present_remote || '|' || object_present_remote "
                       "FROM dr_replication_runs ORDER BY created_at DESC LIMIT 1") == "passed|true|true"
            assert sql("SELECT bool_and(integrity_status='verified') FROM dr_backup_artifacts") == "t"
            shell("run_replication test:manual selected")
            assert sql("SELECT files_copied || '|' || bytes_copied FROM dr_replication_runs "
                       "ORDER BY created_at DESC LIMIT 1") == "0|0"
            print("PASS: cold manual replication and real rclone copy/no-op counters")

            result = shell("scan_backups")
            assert result.stderr.count("verify cached") == 2
            checked = sql("SELECT last_checked_at FROM dr_backup_artifacts WHERE artifact_type='objects'")
            shell("scan_backups")
            assert sql("SELECT last_checked_at FROM dr_backup_artifacts WHERE artifact_type='objects'") == checked
            result = shell("scan_backups true")
            assert "verify cached" not in result.stderr
            key = hashlib.sha256(str(obj).encode()).hexdigest()
            cache = root / "work/cache" / key
            cache.write_text("0\n" + "\n".join(cache.read_text().splitlines()[1:]) + "\n")
            assert "verify start type=objects" in shell("scan_backups").stderr
            print("PASS: unchanged cache, forced scan, 24-hour expiry, truthful last_checked_at")

            original = obj.read_bytes()
            metadata = obj.stat()
            obj.write_bytes(bytes(len(original)))
            os.utime(obj, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            shell("scan_backups", success=False)
            assert sql("SELECT integrity_status FROM dr_backup_artifacts WHERE artifact_type='objects'") == "failed"
            shell("scan_backups", success=False)  # Failed results must never be cached.
            obj.write_bytes(original)
            shell("scan_backups")
            assert "verify start type=objects" in shell("scan_backups true").stderr
            # Database revocation invalidates an otherwise matching local cache.
            sql("UPDATE dr_backup_artifacts SET integrity_status='failed' WHERE artifact_type='objects'")
            assert "verify start type=objects" in shell("scan_backups").stderr
            # An inode replacement, even with size and mtime preserved, is reverified.
            replacement = root / "replacement"
            replacement.write_bytes(original)
            os.utime(replacement, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            replacement.replace(obj)
            assert "verify start type=objects" in shell("scan_backups").stderr
            print("PASS: corruption, preserved mtime/size, failed inventory, inode replacement")

            # Modification during verification cannot publish a verified result.
            command = f"verify_artifact objects {shlex.quote(str(obj))} true"
            shell(command, success=False,
                  prefix=f'openssl() {{ command openssl "$@"; touch {shlex.quote(str(obj))}; }}')
            assert sql("SELECT integrity_error FROM dr_backup_artifacts WHERE artifact_type='objects'") == "artifact changed during verification"
            shell("scan_backups")
            shell(command, success=False, prefix="artifact_upsert() { return 1; }")
            assert not cache.exists()
            shell("scan_backups")
            print("PASS: concurrent modification and database write failure do not cache success")

            # Interrupted backup output and plaintext must never leave the host.
            (obj.parent / "incomplete.enc.partial").write_text("partial")
            (obj.parent / "secret.txt").write_text("plaintext")
            shell("run_replication test:auto all")
            assert sorted(p.suffix for p in (root / "remote").rglob("*.enc")) == [".enc", ".enc"]
            assert not list((root / "remote").rglob("*.partial"))
            assert not list((root / "remote").rglob("*.txt"))
            shell("run_replication test:failure selected", success=False,
                  prefix="rclone() { return 1; }")
            assert sql("SELECT status FROM dr_replication_runs ORDER BY created_at DESC LIMIT 1") == "failed"
            print("PASS: encrypted-only manifests and replication failure status")

            sql("INSERT INTO dr_requests(action,requested_by) VALUES ('replicate','test:queue')")
            result = shell("process_requests", prefix="scan_backups() { exit 99; }")
            assert sql("SELECT status FROM dr_requests") == "completed"
            assert "queue processing" in result.stderr and "queue complete" in result.stderr
            sql("INSERT INTO dr_requests(action,requested_by) VALUES ('scan','test:failure')")
            shell("process_requests", prefix="scan_backups() { return 1; }")
            assert sql("SELECT status FROM dr_requests WHERE action='scan'") == "failed"
            shell("process_requests", success=False, prefix="psql_main() { return 1; }")
            result = shell(loop, prefix='''
process_requests() { echo QUEUE; }
scan_backups() { echo SCAN; }
auto_restore_due() { return 1; }
auto_replication_due() { return 1; }
sleep() { exit 0; }
''')
            assert result.stdout.splitlines() == ["QUEUE", "SCAN", "QUEUE"]
            print("PASS: queue priority, manual replicate bypass, failed request, DB failure")

            # Real isolated restore must fail when pgvector is absent, then clean up.
            shell("run_restore_test test:missing-vector", success=False)
            assert sql("SELECT status FROM dr_restore_tests ORDER BY created_at DESC LIMIT 1") == "failed"
            assert sql("SELECT count(*) FROM pg_database WHERE datname LIKE 'memorybank_dr_%'") == "0"
            assert not (root / "work/restore.dump").exists()
            print("PASS: actual PostgreSQL restore, vector failure gate, temporary DB cleanup")

            # Exercise both writers: a failed encryption must not expose an .enc.
            for service in ("db-backup", "object-backup"):
                for fail in (False, True):
                    destination = root / f"writer-{service}-{fail}"
                    scratch = root / f"scratch-{service}-{fail}"
                    scratch.mkdir()
                    writer = (ROOT / f"ops/{service}/backup.sh").read_text()
                    writer = writer.replace("/tmp/", str(scratch) + "/")
                    writer = writer.replace("/backups", str(destination))
                    wrapper = '''
sleep() { exit 0; }
mc() { return 0; }
openssl() {
  output=""
  previous=""
  for argument in "$@"; do
    if [ "$previous" = -out ]; then output="$argument"; fi
    previous="$argument"
  done
  case "$output" in *.enc.partial) ;; *) return 90 ;; esac
  [ ! -e "${output%.partial}" ] || return 91
'''
                    wrapper += ('  return 1\n}\n' if fail else '  command openssl "$@"\n}\n')
                    writer = writer.replace("set -eu", "set -eu\n" + wrapper, 1)
                    result = run("sh", "-s", input="MINIO_ROOT_USER=test\nMINIO_ROOT_PASSWORD=test\nMINIO_BUCKET=test\n" + writer,
                                 check=False)
                    assert (result.returncode == 0) != fail, result.stderr
                    assert len(list(destination.glob("*.enc"))) == (0 if fail else 1)
            print("PASS: both backup writers publish atomically and hide failed encryption")
        finally:
            run("pg_ctl", "-D", str(root / "pg"), "-m", "immediate", "-w", "stop")


if __name__ == "__main__":
    main()
