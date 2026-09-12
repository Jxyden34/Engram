"use client";

import { FormEvent, useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

export default function ConnectorsPage() {
  const [connectors, setConnectors] = useState<any[]>([]);
  const [runs, setRuns] = useState<any[]>([]);
  const [capabilities, setCapabilities] = useState<any>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [connectorRows, runRows, caps] = await Promise.all([
        api<any[]>("/api/v1/connectors"),
        api<any[]>("/api/v1/connectors/runs?limit=30"),
        api<any>("/api/v1/connectors/capabilities"),
      ]);
      setConnectors(connectorRows);
      setRuns(runRows);
      setCapabilities(caps);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 8000);
    return () => clearInterval(timer);
  }, []);

  async function createConnector(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");

    const f = new FormData(e.currentTarget);
    const repositories = String(f.get("repositories") || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);

    try {
      const connector: any = await api("/api/v1/connectors", {
        method: "POST",
        body: JSON.stringify({
          connector_type: "github",
          name: f.get("name"),
          schedule_minutes: Number(f.get("schedule_minutes")),
          config: {
            installation_id: f.get("installation_id"),
            repositories,
            sync_readme: true,
            sync_docs: Boolean(f.get("sync_docs")),
            sync_issues: Boolean(f.get("sync_issues")),
            sync_pulls: Boolean(f.get("sync_pulls")),
            sync_code: Boolean(f.get("sync_code")),
            max_items_per_sync: Number(f.get("max_items_per_sync")),
          },
        }),
      });

      await api(`/api/v1/connectors/${connector.id}/sync`, { method: "POST" });
      setNotice("GitHub connector created and first sync queued.");
      e.currentTarget.reset();
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function sync(id: string) {
    setBusy(true);
    try {
      await api(`/api/v1/connectors/${id}/sync`, { method: "POST" });
      setNotice("Sync queued.");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(connector: any) {
    try {
      await api(`/api/v1/connectors/${connector.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !connector.enabled }),
      });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this connector? Imported documents and accepted memories remain.")) return;
    try {
      await api(`/api/v1/connectors/${id}`, { method: "DELETE" });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <>
      <Topbar eyebrow="Ingestion mesh" title="Connectors" />

      {error && <div className="errorBox">{error}</div>}
      {notice && <div className="successBox">{notice}</div>}

      <div className="split">
        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panelHead">
            <div>
              <h2>GitHub App</h2>
              <div className="meta">Continuous source sync into the unified Memory Inbox.</div>
            </div>
            <span className={`badge ${capabilities?.github?.available ? "ready" : "failed"}`}>
              {capabilities?.github?.available ? "configured" : "needs credentials"}
            </span>
          </div>

          <div className="meta">App ID</div>
          <div className="codeBlock">
            {capabilities?.github?.app_id_configured ? "configured" : "GITHUB_APP_ID missing"}
          </div>

          <div className="meta" style={{ marginTop: 12 }}>Private key</div>
          <div className="codeBlock">
            {capabilities?.github?.private_key_present
              ? capabilities.github.private_key_path
              : "secrets/github-app.pem is missing"}
          </div>

          <p className="meta" style={{ marginTop: 14 }}>
            Recommended GitHub App repository permissions: Metadata read, Contents read,
            Issues read, Pull requests read. No webhook is required for scheduled sync.
          </p>
        </section>

        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panelHead">
            <div>
              <h2>Browser Capture</h2>
              <div className="meta">Chrome / Edge Manifest V3 extension.</div>
            </div>
            <span className="badge">capture:write</span>
          </div>

          <p className="meta">
            Generate a Browser Capture key under AI & API, then load the extension
            from <code>extensions/memorybank-capture</code>.
          </p>

          <div className="codeBlock" style={{ marginTop: 14 }}>
            Page → Documents → extraction → candidate Memory Inbox
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panelHead">
          <div>
            <h2>Add GitHub connector</h2>
            <div className="meta">Leave repositories blank to sync every repository granted to the App installation.</div>
          </div>
        </div>

        <form className="formGrid" onSubmit={createConnector}>
          <div className="field">
            <label>Name</label>
            <input className="input" name="name" defaultValue="github-main" required />
          </div>

          <div className="field">
            <label>Installation ID</label>
            <input className="input" name="installation_id" placeholder="12345678" required />
          </div>

          <div className="field full">
            <label>Repositories</label>
            <input
              className="input"
              name="repositories"
              placeholder="owner/repo, owner/another-repo — blank = all granted repos"
            />
          </div>

          <div className="field">
            <label>Sync every</label>
            <select className="select" name="schedule_minutes" defaultValue="30">
              <option value="15">15 minutes</option>
              <option value="30">30 minutes</option>
              <option value="60">1 hour</option>
              <option value="360">6 hours</option>
              <option value="1440">Daily</option>
            </select>
          </div>

          <div className="field">
            <label>Maximum items / sync</label>
            <input className="input" type="number" name="max_items_per_sync" min="10" max="2000" defaultValue="300" />
          </div>

          <div className="field full">
            <label>Content</label>
            <div className="row" style={{ flexWrap: "wrap" }}>
              <label className="check"><input type="checkbox" name="sync_docs" defaultChecked /> docs</label>
              <label className="check"><input type="checkbox" name="sync_issues" defaultChecked /> issues</label>
              <label className="check"><input type="checkbox" name="sync_pulls" defaultChecked /> pull requests</label>
              <label className="check"><input type="checkbox" name="sync_code" /> source code</label>
            </div>
          </div>

          <div className="field full">
            <button className="button primary" disabled={busy || !capabilities?.github?.available}>
              Create + sync
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="panelHead">
          <h2>Configured connectors</h2>
          <span className="meta">{connectors.length} total</span>
        </div>

        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>Name</th><th>Status</th><th>Items</th><th>Last sync</th><th>Next sync</th><th></th></tr>
            </thead>
            <tbody>
              {connectors.map((c) => (
                <tr key={c.id}>
                  <td>
                    <strong>{c.name}</strong>
                    <div className="meta">GitHub · every {c.schedule_minutes}m</div>
                  </td>
                  <td>
                    <span className={`badge ${c.last_status || ""}`}>
                      {!c.enabled ? "paused" : c.last_status || "new"}
                    </span>
                    {c.last_error && <div className="meta">{c.last_error}</div>}
                  </td>
                  <td>{c.item_count}</td>
                  <td className="meta">{dateText(c.last_sync_at)}</td>
                  <td className="meta">{dateText(c.next_sync_at)}</td>
                  <td>
                    <div className="row">
                      <button className="ghostButton" disabled={busy} onClick={() => sync(c.id)}>Sync</button>
                      <button className="ghostButton" onClick={() => toggle(c)}>{c.enabled ? "Pause" : "Resume"}</button>
                      <button className="dangerButton" onClick={() => remove(c.id)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panelHead">
          <h2>Recent sync runs</h2>
          <span className="meta">{runs.length} shown</span>
        </div>
        <div className="tableWrap">
          <table>
            <thead><tr><th>Connector</th><th>Status</th><th>Seen</th><th>Changed</th><th>Skipped</th><th>Started</th></tr></thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td><strong>{run.connector_name}</strong></td>
                  <td><span className={`badge ${run.status}`}>{run.status}</span></td>
                  <td>{run.items_seen}</td>
                  <td>{run.items_changed}</td>
                  <td>{run.items_skipped}</td>
                  <td className="meta">{dateText(run.started_at || run.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
