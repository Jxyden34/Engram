"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

type Notice = {
  id: string; title: string; detail: string; href: string; severity: string;
  kind: string; created_at: string; read_at: string | null; dismissed_at: string | null;
};
type Inbox = { items: Notice[]; unread: number };

export default function NotificationsPage() {
  const [telegram, setTelegram] = useState({ enabled: false, chat_id: "", available: false, delivered: 0, retrying: 0 });
  const [notice, setNotice] = useState("");
  useEffect(() => { api<typeof telegram>("/api/v1/notifications/telegram").then(setTelegram).catch(e => setError(e.message)); }, []);
  const [data, setData] = useState<Inbox | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [includeDismissed, setIncludeDismissed] = useState(false);
  const [filter, setFilter] = useState("all");

  async function load(dismissed: boolean) {
    setError("");
    try {
      const inbox = await api<Inbox>("/api/v1/notifications?dismissed=" + dismissed);
      setData(inbox);
      window.dispatchEvent(new CustomEvent("engram-notifications", {detail:inbox.unread}));
    }
    catch (e: any) { setError(e.message); }
  }
  useEffect(() => { void load(includeDismissed); }, [includeDismissed]);

  async function act(path: string) {
    setBusy(true);
    setError("");
    try {
      await api(path, { method: "POST" });
      await load(includeDismissed);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  const items = data?.items.filter(item => filter === "all" || filter === "unread" && !item.read_at && !item.dismissed_at || item.severity === filter) || [];
  return <>
    <Topbar eyebrow="Project activity" title="Notifications" />
    <details className="panel">
      <summary>Telegram delivery</summary>
      <p className="meta">{telegram.available ? "Bot configured on this server." : "Set TELEGRAM_BOT_TOKEN in the server environment to enable delivery."}</p>
      <form className="formGrid" onSubmit={async e => {
        e.preventDefault(); setBusy(true); setError(""); setNotice("");
        try {
          setTelegram(await api<typeof telegram>("/api/v1/notifications/telegram", { method: "PUT", body: JSON.stringify({enabled: telegram.enabled, chat_id: telegram.chat_id}) }));
          setNotice("Telegram settings saved.");
        } catch (e: any) { setError(e.message); } finally { setBusy(false); }
      }}>
        <label className="field"><span>Chat ID</span><input className="input" value={telegram.chat_id} pattern="-?[0-9]{1,20}" required onChange={e => setTelegram({...telegram, chat_id:e.target.value})} /></label>
        <label><input type="checkbox" checked={telegram.enabled} onChange={e => setTelegram({...telegram,enabled:e.target.checked})} /> Deliver this project's notifications</label>
        <button className="button" disabled={busy}>Save Telegram settings</button>
        <button type="button" className="ghostButton" disabled={busy || !telegram.available} onClick={async () => {
          setBusy(true); setError(""); setNotice("");
          try { await api("/api/v1/notifications/telegram/test", {method:"POST"}); setNotice("Test message sent."); }
          catch(e:any) { setError(e.message); } finally {setBusy(false);}
        }}>Send test message</button>
      </form>
      <p className="meta">{telegram.delivered} delivered · {telegram.retrying} awaiting retry</p>
    </details>
    {notice && <p className="successBox" role="status">{notice}</p>}
    <section className="panel">
      <div className="panelHead">
        <div><h2>{data ? data.unread + " unread" : "Project notifications"}</h2>
          <p className="meta">Operational issues and memories that need your attention.</p></div>
        <button className="button primary" disabled={busy} onClick={() => act("/api/v1/notifications/refresh")}>{busy ? "Updating…" : "Check now"}</button>
      </div>
      <div className="row" style={{ flexWrap: "wrap", marginBottom: 18 }}>
        <label className="field"><span>Show</span>
          <select className="select" value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="all">All notifications</option><option value="unread">Unread</option><option value="critical">Critical</option><option value="warning">Warnings</option><option value="info">Information</option>
          </select>
        </label>
        <label><input type="checkbox" checked={includeDismissed} onChange={e => setIncludeDismissed(e.target.checked)} /> Include dismissed</label>
      </div>
      {error && <p className="errorBox" role="alert">{error}</p>}
      {!data && !error && <p className="empty" role="status">Loading notifications…</p>}
      {data && items.length === 0 && <p className="empty">No notifications in this view.</p>}
      {items.map(item => <article className="notificationCard" key={item.id}>
        <div className="panelHead">
          <h3>{item.title}</h3>
          <span className={"badge " + (item.severity === "critical" ? "failed" : item.severity === "warning" ? "pending" : "")}>{item.severity}</span>
        </div>
        <p>{item.detail}</p>
        <p className="meta">{dateText(item.created_at)} · {item.dismissed_at ? "Dismissed" : item.read_at ? "Read" : "Unread"}</p>
        <div className="row" style={{ flexWrap: "wrap" }}>
          <Link className="button" href={item.href} onClick={() => { void act("/api/v1/notifications/" + item.id + "/read"); }}>Review source</Link>
          {!item.read_at && <button className="ghostButton" disabled={busy} onClick={() => act("/api/v1/notifications/" + item.id + "/read")}>Mark read</button>}
          {!item.dismissed_at && <button className="ghostButton" disabled={busy} onClick={() => act("/api/v1/notifications/" + item.id + "/dismiss")}>Dismiss</button>}
        </div>
      </article>)}
    </section>
  </>;
}
