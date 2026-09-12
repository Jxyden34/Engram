"use client";

import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

function bytes(value: number | null | undefined) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = value;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i < 2 ? 1 : 2)} ${units[i]}`;
}

export default function DisasterRecoveryPage() {
  const [summary, setSummary] = useState<any>(null);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [tests, setTests] = useState<any[]>([]);
  const [replication, setReplication] = useState<any[]>([]);
  const [requests, setRequests] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  async function load() {
    try {
      const [s, a, t, r, q] = await Promise.all([
        api<any>("/api/v1/dr/summary"),
        api<any[]>("/api/v1/dr/artifacts?limit=50"),
        api<any[]>("/api/v1/dr/restore-tests?limit=30"),
        api<any[]>("/api/v1/dr/replication-runs?limit=30"),
        api<any[]>("/api/v1/dr/requests?limit=20"),
      ]);
      setSummary(s);
      setArtifacts(a);
      setTests(t);
      setReplication(r);
      setRequests(q);
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 10000);
    return () => clearInterval(timer);
  }, []);

  async function action(name: "scan" | "restore-test" | "replicate") {
    setBusy(name);
    setNotice("");
    setError("");
    try {
      await api(`/api/v1/dr/${name}`, { method: "POST" });
      setNotice(
        name === "scan"
          ? "Backup verification queued."
          : name === "restore-test"
          ? "Isolated restore test queued."
          : "Off-site replication queued."
      );
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <Topbar eyebrow="Resilience" title="Disaster Recovery" />

      {error && <div className="errorBox">{error}</div>}
      {notice && <div className="successBox">{notice}</div>}

      {summary && (
        <>
          <div className="healthHero">
            <div className={`healthScore score-${summary.score >= 90 ? "good" : summary.score >= 65 ? "warn" : "bad"}`}>
              {summary.score}<span>/100</span>
            </div>
            <div>
              <h2>{summary.overall === "healthy" ? "Recovery posture healthy" : summary.overall === "warning" ? "Recovery posture needs attention" : "Recovery posture at risk"}</h2>
              <p>
                Evidence from encrypted backups, integrity checks, isolated restores,
                off-site copies and backup filesystem health.
              </p>
            </div>
            <div className="row" style={{ flexWrap: "wrap" }}>
              <button className="button" disabled={Boolean(busy)} onClick={() => action("scan")}>
                {busy === "scan" ? "Scanning…" : "Verify backups"}
              </button>
              <button className="button primary" disabled={Boolean(busy)} onClick={() => action("restore-test")}>
                {busy === "restore-test" ? "Queued…" : "Run restore test"}
              </button>
              <button
                className="button"
                disabled={Boolean(busy) || !summary.config.offsite_enabled}
                onClick={() => action("replicate")}
              >
                {busy === "replicate" ? "Queued…" : "Replicate off-site"}
              </button>
            </div>
          </div>

          <div className="healthIssues">
            {summary.checks.map((check: any) => (
              <div className={`healthIssue ${check.status === "critical" ? "high" : check.status === "warning" ? "medium" : "ok"}`} key={check.key}>
                <span className="healthDot" />
                <div>
                  <strong>{check.label}</strong>
                  <div className="meta">{check.detail}</div>
                </div>
                <b>{check.status}</b>
              </div>
            ))}
          </div>

          <div className="grid4" style={{ marginTop: 18 }}>
            <div className="miniStat">
              <span>PostgreSQL archives</span>
              <strong>{summary.counts.postgres_artifacts}</strong>
            </div>
            <div className="miniStat">
              <span>Object archives</span>
              <strong>{summary.counts.object_artifacts}</strong>
            </div>
            <div className="miniStat">
              <span>Passed restore tests</span>
              <strong>{summary.counts.passed_restore_tests}</strong>
            </div>
            <div className="miniStat">
              <span>Failed restore tests</span>
              <strong>{summary.counts.failed_restore_tests}</strong>
            </div>
          </div>
        </>
      )}

      <section className="panel">
        <div className="panelHead">
          <div>
            <h2>Latest recovery evidence</h2>
            <div className="meta">A backup only earns a green badge after decrypt + integrity validation.</div>
          </div>
        </div>

        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>Type</th><th>Artifact</th><th>Size</th><th>Integrity</th><th>Created</th><th>Retention</th></tr>
            </thead>
            <tbody>
              {artifacts.map((artifact) => (
                <tr key={artifact.id}>
                  <td><span className="badge">{artifact.artifact_type}</span></td>
                  <td>
                    <strong>{artifact.file_name}</strong>
                    <div className="meta">{artifact.sha256 ? `sha256 ${artifact.sha256.slice(0, 16)}…` : "hash pending"}</div>
                  </td>
                  <td>{bytes(artifact.size_bytes)}</td>
                  <td>
                    <span className={`badge ${artifact.integrity_status === "verified" ? "ready" : artifact.integrity_status === "failed" ? "failed" : ""}`}>
                      {artifact.integrity_status}
                    </span>
                    {artifact.integrity_error && <div className="meta">{artifact.integrity_error}</div>}
                  </td>
                  <td className="meta">{dateText(artifact.artifact_created_at)}</td>
                  <td className="meta">{dateText(artifact.retention_until)}</td>
                </tr>
              ))}
              {!artifacts.length && <tr><td colSpan={6} className="meta">The DR monitor has not inventoried any backups yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panelHead">
          <div>
            <h2>Restore tests</h2>
            <div className="meta">PostgreSQL is restored into a disposable database. Production is never overwritten.</div>
          </div>
        </div>

        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>Status</th><th>Database</th><th>Objects</th><th>Rows</th><th>Missing refs</th><th>Duration</th><th>Completed</th></tr>
            </thead>
            <tbody>
              {tests.map((test) => (
                <tr key={test.id}>
                  <td><span className={`badge ${test.status}`}>{test.status}</span></td>
                  <td>
                    <strong>{test.postgres_restore_ok ? "restored" : "failed"}</strong>
                    <div className="meta">{test.vector_extension_ok ? "pgvector verified" : "pgvector unverified"}</div>
                  </td>
                  <td>
                    <strong>{test.object_extract_ok ? "extractable" : "not verified"}</strong>
                    <div className="meta">{test.object_file_count ?? 0} files</div>
                  </td>
                  <td className="meta">
                    {test.memory_count ?? 0} memories<br />
                    {test.document_count ?? 0} documents
                  </td>
                  <td>{test.missing_object_refs ?? 0}</td>
                  <td>{test.duration_seconds != null ? `${test.duration_seconds}s` : "—"}</td>
                  <td className="meta">
                    {dateText(test.completed_at || test.created_at)}
                    {test.error_message && <div>{test.error_message}</div>}
                  </td>
                </tr>
              ))}
              {!tests.length && <tr><td colSpan={7} className="meta">No restore test has run yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <div className="split">
        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panelHead"><h2>Off-site replication</h2></div>
          {!summary?.config?.offsite_enabled && (
            <div className="empty">
              Disabled. Configure <code>DR_OFFSITE_REMOTE</code> and <code>secrets/rclone.conf</code> to enable encrypted off-host copies.
            </div>
          )}
          {replication.slice(0, 10).map((run) => (
            <div className="healthMemory" key={run.id}>
              <strong>{run.status} · {run.target || "not configured"}</strong>
              <span>
                DB {run.postgres_present_remote ? "✓" : "·"} · objects {run.object_present_remote ? "✓" : "·"} · {dateText(run.completed_at || run.created_at)}
              </span>
            </div>
          ))}
        </section>

        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panelHead"><h2>DR activity</h2></div>
          {requests.map((request) => (
            <div className="healthMemory" key={request.id}>
              <strong>{request.action}</strong>
              <span>{request.status} · {request.requested_by} · {dateText(request.created_at)}</span>
            </div>
          ))}
          {!requests.length && <div className="empty">No manual DR actions yet.</div>}
        </section>
      </div>
    </>
  );
}
