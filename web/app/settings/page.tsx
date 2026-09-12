"use client";

import { FormEvent, useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

const AI_SCOPES = ["memory:read", "memory:write", "memory:delete_request", "document:read", "mcp:use"];
const CAPTURE_SCOPES = ["capture:write"];
const OAUTH_SCOPES = ["mcp:use", "memory:read", "document:read", "memory:write", "memory:delete_request"];

export default function SettingsPage() {
  const [keys, setKeys] = useState<any[]>([]);
  const [oauthClients, setOauthClients] = useState<any[]>([]);
  const [grants, setGrants] = useState<any[]>([]);
  const [oauthSummary, setOauthSummary] = useState<any>(null);
  const [newToken, setNewToken] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    try {
      const [keyRows, clients, grantRows, summary] = await Promise.all([
        api<any[]>("/api/v1/keys"),
        api<any[]>("/api/v1/oauth/clients"),
        api<any[]>("/api/v1/oauth/grants"),
        api<any>("/api/v1/oauth/summary"),
      ]);
      setKeys(keyRows);
      setOauthClients(clients);
      setGrants(grantRows);
      setOauthSummary(summary);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function createKey(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      const result: any = await api("/api/v1/keys", {
        method: "POST",
        body: JSON.stringify({ name: form.get("name"), scopes: AI_SCOPES }),
      });
      setNewToken(result.token);
      await load();
    } catch (e: any) { setError(e.message); }
  }

  async function createCaptureKey() {
    try {
      const result: any = await api("/api/v1/keys", {
        method: "POST",
        body: JSON.stringify({ name: "browser-capture", scopes: CAPTURE_SCOPES }),
      });
      setNewToken(result.token);
      await load();
    } catch (e: any) { setError(e.message); }
  }

  async function revoke(id: string) {
    if (!confirm("Revoke this key? Any connected client using it will immediately lose access.")) return;
    try {
      await api(`/api/v1/keys/${id}`, { method: "DELETE" });
      await load();
    } catch (e: any) { setError(e.message); }
  }

  async function createOAuthClient(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setNotice("");
    const form = new FormData(e.currentTarget);
    const redirectUris = String(form.get("redirect_uris") || "")
      .split("\n")
      .map((value) => value.trim())
      .filter(Boolean);
    const allowedScopes = OAUTH_SCOPES.filter((scope) => form.get(`scope:${scope}`));

    try {
      const row: any = await api("/api/v1/oauth/clients", {
        method: "POST",
        body: JSON.stringify({
          client_name: form.get("client_name"),
          redirect_uris: redirectUris,
          allowed_scopes: allowedScopes,
        }),
      });
      setNotice(`OAuth client created: ${row.client_id}`);
      e.currentTarget.reset();
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function revokeOAuthClient(clientId: string) {
    if (!confirm("Disable this OAuth client and revoke all of its access and refresh tokens?")) return;
    try {
      await api(`/api/v1/oauth/clients/${encodeURIComponent(clientId)}`, { method: "DELETE" });
      setNotice("OAuth client revoked.");
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function revokeGrant(id: string) {
    if (!confirm("Revoke this authorization grant and all tokens issued under it?")) return;
    try {
      await api(`/api/v1/oauth/grants/${id}`, { method: "DELETE" });
      setNotice("OAuth grant revoked.");
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <>
      <Topbar eyebrow="Machine access" title="AI, API & OAuth" />

      {error && <div className="errorBox">{error}</div>}
      {notice && <div className="successBox">{notice}</div>}

      <div className="split">
        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panelHead">
            <div>
              <h2>MCP OAuth</h2>
              <div className="meta">Recommended for interactive AI clients.</div>
            </div>
            <span className="badge ready">v2.2</span>
          </div>

          <div className="meta">MCP resource</div>
          <div className="codeBlock">{oauthSummary?.resource || "Loading…"}</div>

          <div className="meta" style={{ marginTop: 12 }}>Protected Resource Metadata</div>
          <div className="codeBlock">{oauthSummary?.resource_metadata || "Loading…"}</div>

          <div className="meta" style={{ marginTop: 12 }}>Authorization Server Metadata</div>
          <div className="codeBlock">{oauthSummary?.oauth_metadata || "Loading…"}</div>

          <div className="row" style={{ marginTop: 14, flexWrap: "wrap" }}>
            <span className="badge">{oauthSummary?.access_token_minutes ?? "?"}m access tokens</span>
            <span className="badge">{oauthSummary?.refresh_token_days ?? "?"}d refresh tokens</span>
            <span className="badge">{oauthSummary?.cimd_supported ? "CIMD" : "no CIMD"}</span>
            <span className="badge">{oauthSummary?.dcr_enabled ? "DCR fallback" : "DCR off"}</span>
          </div>
        </section>

        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panelHead"><h2>Legacy API key</h2><span className="badge">scripts / fallback</span></div>
          <p className="meta">
            API keys remain supported for scripts and older clients. Interactive MCP clients should prefer OAuth.
          </p>
          <form className="row" onSubmit={createKey} style={{ marginTop: 18 }}>
            <input className="input" name="name" placeholder="e.g. automation-script" required />
            <button className="button primary">Generate key</button>
          </form>

          {newToken && (
            <div className="successBox">
              <strong>Copy this now. It will not be shown again.</strong><br /><br />{newToken}
            </div>
          )}
        </section>
      </div>

      <section className="panel">
        <div className="panelHead">
          <div>
            <h2>Pre-register OAuth client</h2>
            <div className="meta">Useful when an MCP client does not publish a Client ID Metadata Document.</div>
          </div>
        </div>

        <form className="formGrid" onSubmit={createOAuthClient}>
          <div className="field">
            <label>Client name</label>
            <input className="input" name="client_name" placeholder="Claude Desktop / ChatGPT / local client" required />
          </div>

          <div className="field">
            <label>Redirect URIs</label>
            <textarea
              className="input"
              name="redirect_uris"
              rows={4}
              placeholder={"http://127.0.0.1:3000/callback\nhttps://client.example.com/oauth/callback"}
              required
            />
          </div>

          <div className="field full">
            <label>Allowed scopes</label>
            <div className="row" style={{ flexWrap: "wrap" }}>
              {OAUTH_SCOPES.map((scope) => (
                <label className="check" key={scope}>
                  <input
                    type="checkbox"
                    name={`scope:${scope}`}
                    defaultChecked={["mcp:use", "memory:read", "document:read"].includes(scope)}
                  />
                  {scope}
                </label>
              ))}
            </div>
          </div>

          <div className="field full">
            <button className="button primary">Create OAuth client</button>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="panelHead">
          <h2>OAuth clients</h2>
          <span className="meta">{oauthClients.filter((c) => c.is_active).length} active</span>
        </div>

        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>Client</th><th>Type</th><th>Scopes</th><th>Tokens</th><th>Last used</th><th></th></tr>
            </thead>
            <tbody>
              {oauthClients.map((client) => (
                <tr key={client.client_id}>
                  <td>
                    <strong>{client.client_name}</strong>
                    <div className="meta" style={{ maxWidth: 330, overflowWrap: "anywhere" }}>
                      {client.client_id}
                    </div>
                    {!client.is_active && <div className="meta">revoked</div>}
                  </td>
                  <td><span className="badge">{client.registration_type}</span></td>
                  <td className="meta">{client.allowed_scopes.join(", ")}</td>
                  <td className="meta">
                    {client.active_access_tokens} access / {client.active_refresh_tokens} refresh
                  </td>
                  <td className="meta">{dateText(client.token_last_used_at || client.last_used_at)}</td>
                  <td>
                    {client.is_active && (
                      <button className="dangerButton" onClick={() => revokeOAuthClient(client.client_id)}>
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!oauthClients.length && (
                <tr><td colSpan={6} className="meta">No OAuth clients have connected yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panelHead">
          <h2>Authorized clients</h2>
          <span className="meta">{grants.filter((g) => !g.revoked_at).length} active grants</span>
        </div>
        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>Client</th><th>User</th><th>Scopes</th><th>Authorized</th><th>Tokens</th><th></th></tr>
            </thead>
            <tbody>
              {grants.map((grant) => (
                <tr key={grant.id}>
                  <td>
                    <strong>{grant.client_name}</strong>
                    <div className="meta">{grant.registration_type}</div>
                  </td>
                  <td>{grant.username}</td>
                  <td className="meta">{grant.scopes.join(", ")}</td>
                  <td className="meta">{dateText(grant.authorized_at)}</td>
                  <td className="meta">
                    {grant.active_access_tokens} access / {grant.active_refresh_tokens} refresh
                  </td>
                  <td>
                    {!grant.revoked_at && (
                      <button className="dangerButton" onClick={() => revokeGrant(grant.id)}>
                        Revoke grant
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!grants.length && (
                <tr><td colSpan={6} className="meta">No clients have been authorized yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="split">
        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panelHead"><h2>Browser Capture</h2><span className="badge">write-only</span></div>
          <p className="meta">Generate a key that can only send captures into MemoryBank.</p>
          <button className="button primary" onClick={createCaptureKey}>Generate capture key</button>
          <div className="meta" style={{ marginTop: 12 }}>Scope</div>
          <div className="codeBlock">capture:write</div>
        </section>

        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panelHead"><h2>Remote MCP</h2><span className="badge ready">OAuth preferred</span></div>
          <div className="meta">Endpoint</div>
          <div className="codeBlock">{oauthSummary?.resource || "https://YOUR-HOST/mcp"}</div>
          <p className="meta" style={{ marginTop: 12 }}>
            Modern MCP clients can discover OAuth automatically from the protected resource metadata.
            Legacy Bearer API keys still work.
          </p>
        </section>
      </div>

      <section className="panel">
        <div className="panelHead">
          <h2>Legacy API credentials</h2>
          <span className="meta">{keys.filter((k) => !k.revoked_at).length} active</span>
        </div>
        <div className="tableWrap">
          <table>
            <thead><tr><th>Name</th><th>Prefix</th><th>Scopes</th><th>Last used</th><th></th></tr></thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id}>
                  <td>
                    <strong>{k.name}</strong>
                    {k.revoked_at && <div className="meta">revoked {dateText(k.revoked_at)}</div>}
                  </td>
                  <td><span className="kbd">{k.key_prefix}…</span></td>
                  <td className="meta">{k.scopes.join(", ")}</td>
                  <td className="meta">{dateText(k.last_used_at)}</td>
                  <td>
                    {!k.revoked_at && <button className="dangerButton" onClick={() => revoke(k.id)}>Revoke</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
