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
  const [editing, setEditing] = useState<any>(null);

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
    const gmail = new URLSearchParams(window.location.search).get("gmail");
    if (gmail === "connected") setNotice("Gmail connected. Your first sync will start shortly.");
    if (gmail === "cancelled") setNotice("Gmail connection was cancelled.");
    const timer = setInterval(() => void load(), 8000);
    return () => clearInterval(timer);
  }, []);

  async function connectGmail(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    const label = String(f.get("label") || "INBOX");
    try {
      const result: any = await api("/api/v1/connectors/gmail/authorize", {
        method: "POST",
        body: JSON.stringify({
          name: "Gmail",
          query: String(f.get("query") || "newer_than:30d"),
          label_ids: label === "ALL" ? [] : [label],
          max_messages_per_sync: Number(f.get("max_messages_per_sync")),
        }),
      });
      window.location.assign(result.authorization_url);
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  }

  async function createConnector(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");

    const form = e.currentTarget;
    const f = new FormData(form);
    const repositories = String(f.get("repositories") || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);

    try {
      const branches = Object.fromEntries(
        String(f.get("branches") || "").split(/\r?\n/).map(value => value.trim()).filter(Boolean).map(value => {
          const separator = value.indexOf("=");
          if (separator < 1 || !value.slice(separator + 1).trim()) {
            throw new Error("Use owner/repo=branch for each branch selection.");
          }
          return [value.slice(0, separator).trim(), value.slice(separator + 1).trim()];
        })
      );
      const repositoryContent = Object.fromEntries(
        String(f.get("repository_content") || "").split(/\r?\n/).map(value => value.trim()).filter(Boolean).map(value => {
          const separator = value.indexOf("=");
          if (separator < 1) throw new Error("Use owner/repo=content types for each repository filter.");
          return [value.slice(0, separator).trim(), value.slice(separator + 1).split(",").map(source => source.trim()).filter(Boolean)];
        })
      );
      const connector: any = await api(editing ? `/api/v1/connectors/${editing.id}` : "/api/v1/connectors", {
        method: editing ? "PATCH" : "POST",
        body: JSON.stringify({
          connector_type: "github",
          name: f.get("name"),
          schedule_minutes: Number(f.get("schedule_minutes")),
          config: {
            ...editing?.config,
            installation_id: f.get("installation_id"),
            repositories,
            branches,
            repository_content: repositoryContent,
            ignore_patterns: String(f.get("ignore_patterns") || "").split(/\r?\n/).map(value => value.trim()).filter(Boolean),
            code_extensions: String(f.get("code_extensions") || "").split(",").map(value => value.trim()).filter(Boolean),
            sync_readme: Boolean(f.get("sync_readme")),
            sync_docs: Boolean(f.get("sync_docs")),
            sync_issues: Boolean(f.get("sync_issues")),
            sync_pulls: Boolean(f.get("sync_pulls")),
            sync_code: Boolean(f.get("sync_code")),
            sync_commits: Boolean(f.get("sync_commits")),
            sync_releases: Boolean(f.get("sync_releases")),
            sync_discussions: Boolean(f.get("sync_discussions")),
            max_items_per_sync: Number(f.get("max_items_per_sync")),
          },
        }),
      });

      if (editing) {
        setNotice("GitHub connector settings saved.");
        setEditing(null);
      } else {
        await api(`/api/v1/connectors/${connector.id}/sync`, { method: "POST" });
        setNotice("GitHub connector created and first sync queued.");
        form.reset();
      }
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

  function editConnector(connector: any) {
    setEditing(connector);
    setError("");
    document.getElementById("github-connector-form")?.scrollIntoView({block: "start"});
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
              <h2>Gmail</h2>
              <div className="meta">Read only sync of selected Gmail messages.</div>
            </div>
            <span className={`badge ${capabilities?.gmail?.available ? "ready" : "failed"}`}>
              {capabilities?.gmail?.available ? "configured" : "needs Google OAuth setup"}
            </span>
          </div>
          <p className="meta">
            Requests Google’s Gmail read-only access. Messages become source documents;
            attachments are not imported. Google may require OAuth app verification.
          </p>
          {capabilities?.gmail?.redirect_uri && (
            <><div className="meta">Authorized redirect URI for your Google OAuth web client</div>
              <div className="codeBlock">{capabilities.gmail.redirect_uri}</div></>
          )}
          <form className="formGrid" onSubmit={connectGmail}>
            <div className="field full">
              <label>Gmail search</label>
              <input className="input" name="query" defaultValue="newer_than:30d" maxLength={1000} />
            </div>
            <div className="field">
              <label>Mail to sync</label>
              <select className="select" name="label" defaultValue="INBOX">
                <option value="INBOX">Inbox</option>
                <option value="STARRED">Starred</option>
                <option value="ALL">All mail matching search</option>
              </select>
            </div>
            <div className="field">
              <label>Maximum messages per sync</label>
              <input className="input" type="number" name="max_messages_per_sync" min="1" max="500" defaultValue="100" />
            </div>
            <div className="field full">
              <button className="button primary" disabled={busy || !capabilities?.gmail?.available}>
                Connect Gmail
              </button>
            </div>
          </form>
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
            Generate a Browser Capture key under Personal API Gateway, then load the extension
            from <code>extensions/engram-capture</code>.
          </p>

          <div className="codeBlock" style={{ marginTop: 14 }}>
            Page → Documents → extraction → candidate Memory Inbox
          </div>
        </section>
      </div>

      <section className="panel" id="github-connector-form">
        <div className="panelHead">
          <div>
            <h2>{editing ? `Edit ${editing.name}` : "Add GitHub connector"}</h2>
            <div className="meta">Leave repositories blank to sync every repository granted to the App installation.</div>
          </div>
        </div>

        <form key={editing?.id ?? "new"} className="formGrid" onSubmit={createConnector}>
          <div className="field">
            <label>Name</label>
            <input className="input" name="name" defaultValue={editing?.name ?? "github-main"} required />
          </div>

          <div className="field">
            <label>Installation ID</label>
            <input className="input" name="installation_id" defaultValue={editing?.config.installation_id} placeholder="12345678" required />
          </div>

          <div className="field full">
            <label>Repositories</label>
            <input
              className="input"
              name="repositories"
              defaultValue={editing?.config.repositories?.join(", ")}
              placeholder="owner/repo, owner/another-repo — blank = all granted repos"
            />
          </div>

          <div className="field">
            <label>Sync every</label>
            <select className="select" name="schedule_minutes" defaultValue={editing?.schedule_minutes ?? 30}>
              {editing && ![15,30,60,360,1440].includes(editing.schedule_minutes) && (
                <option value={editing.schedule_minutes}>{editing.schedule_minutes} minutes</option>
              )}
              <option value="15">15 minutes</option>
              <option value="30">30 minutes</option>
              <option value="60">1 hour</option>
              <option value="360">6 hours</option>
              <option value="1440">Daily</option>
            </select>
          </div>

          <div className="field">
            <label>Maximum items / sync</label>
            <input className="input" type="number" name="max_items_per_sync" min="10" max="2000" defaultValue={editing?.config.max_items_per_sync ?? 300} />
          </div>

          <div className="field full">
            <label>Content</label>
            <div className="row" style={{ flexWrap: "wrap" }}>
              {Object.entries({readme:"README", docs:"docs", issues:"issues", pulls:"pull requests", code:"source code", commits:"commits", releases:"releases", discussions:"discussions"}).map(([source, label]) => (
                <label className="check" key={source}>
                  <input type="checkbox" name={`sync_${source}`} defaultChecked={editing?.config[`sync_${source}`] ?? ["readme","docs","issues","pulls"].includes(source)} /> {label}
                </label>
              ))}
            </div>
          </div>

          <div className="field full">
            <label htmlFor="github-branches">Branch overrides for listed repositories</label>
            <textarea className="textarea" id="github-branches" name="branches" placeholder="owner/repo=release/current"
              defaultValue={Object.entries(editing?.config.branches ?? {}).map(([repo, branch]) => `${repo}=${branch}`).join("\n")} />
          </div>
          <div className="field full">
            <label htmlFor="github-content">Content overrides for listed repositories</label>
            <textarea className="textarea" id="github-content" name="repository_content" placeholder="owner/repo=readme,docs,releases"
              defaultValue={Object.entries(editing?.config.repository_content ?? {}).map(([repo, types]) => `${repo}=${types}`).join("\n")} />
            <div className="meta">Types: readme, docs, issues, pulls, code, commits, releases, discussions.</div>
          </div>
          <div className="field">
            <label htmlFor="github-ignore">Ignore file patterns (one per line)</label>
            <textarea className="textarea" id="github-ignore" name="ignore_patterns" placeholder="vendor/*" defaultValue={editing?.config.ignore_patterns?.join("\n")} />
          </div>
          <div className="field">
            <label htmlFor="github-extensions">Source file extensions</label>
            <input className="input" id="github-extensions" name="code_extensions" placeholder=".py, .ts" defaultValue={editing?.config.code_extensions?.join(", ")} />
          </div>

          <div className="field full">
            <button className="button primary" disabled={busy || !capabilities?.github?.available}>
              {editing ? "Save settings" : "Create + sync"}
            </button>
            {editing && <button className="ghostButton" type="button" disabled={busy} onClick={() => setEditing(null)}>Cancel</button>}
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
                    <div className="meta">{c.connector_type === "gmail" ? "Gmail" : "GitHub"} · every {c.schedule_minutes}m</div>
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
                      {c.connector_type === "github" && <button className="ghostButton" disabled={busy} onClick={() => editConnector(c)}>Edit</button>}
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
            <thead><tr><th>Connector</th><th>Status</th><th>Seen</th><th>Changed</th><th>Skipped</th><th>Errors</th><th>Started</th><th>Completed</th></tr></thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td><strong>{run.connector_name}</strong></td>
                  <td>
                    <span className={`badge ${run.status === "ready" && run.error_count > 0 ? "warn" : run.status}`}>
                      {run.status === "ready" && run.error_count > 0 ? "Completed with errors" : run.status}
                    </span>
                    {run.error_message && <div className="meta">{run.error_message}</div>}
                  </td>
                  <td>{run.items_seen}</td>
                  <td>{run.items_changed}</td>
                  <td>{run.items_skipped}</td>
                  <td>{run.error_count}</td>
                  <td className="meta">{dateText(run.started_at || run.created_at)}</td>
                  <td className="meta">{run.completed_at ? dateText(run.completed_at) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
