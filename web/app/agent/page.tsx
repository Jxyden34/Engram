"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/Topbar";
import ClusterConsolidation from '@/components/ClusterConsolidation';
import LifecycleHistory from '@/components/LifecycleHistory';
import { api, dateText } from "@/lib/api";
import styles from "./agent.module.css";

type Draft = { safe_to_merge: boolean; title?: string; content?: string; reason: string; source_memory_ids: string[]; source_updated_at: string[]; quotes?: { source: number; quote: string }[] };
type Proposal = { id: string; proposal_type: string; memory_id: string; memory_title: string; related_memory_id?: string; related_title?: string; reason: string; created_at: string; evidence?: { draft?: Draft }; draft_stale?: boolean };
type ScanRun = { id: string; trigger_type: string; status: string; result?: { total: number }; error_message?: string; created_at: string };
type Schedule = { enabled: boolean; interval_hours: number; next_scan_at?: string | null };

const views = [
  ["review", "Review queue"],
  ["consolidate", "Group consolidation"],
  ["activity", "Scans & schedule"],
  ["history", "Lifecycle history"],
] as const;

export default function AgentPage() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [runs, setRuns] = useState<ScanRun[]>([]);
  const [schedule, setSchedule] = useState<Schedule>({ enabled: false, interval_hours: 24 });
  const [currentSchedule, setCurrentSchedule] = useState(schedule);
  const [isAdmin, setIsAdmin] = useState(false);
  const [view, setView] = useState<(typeof views)[number][0]>("review");
  const [loaded, setLoaded] = useState(false);
  const [action, setAction] = useState<"scan" | "schedule" | "approve" | null>(null);
  const busy = action !== null;
  const [draftingId, setDraftingId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    try {
      const [items, history, current, me] = await Promise.all([
        api<Proposal[]>("/api/v1/agent/proposals"),
        api<ScanRun[]>("/api/v1/agent/runs"),
        api<Schedule>("/api/v1/agent/schedule"),
        api<{ is_admin: boolean }>("/api/v1/auth/me"),
      ]);
      setProposals(items);
      setRuns(history);
      setSchedule(current);
      setCurrentSchedule(current);
      setIsAdmin(me.is_admin);
      setLoaded(true);
    }
    catch (e: any) { setError(e.message); }
  }
  useEffect(() => { void load(); }, []);
  async function scan() {
    setAction("scan"); setError(""); setNotice("");
    try {
      const result = await api<{ total: number }>("/api/v1/agent/scan", { method: "POST" });
      setNotice(`${result.total} new proposal${result.total === 1 ? "" : "s"}.`);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setAction(null); }
  }
  async function dismiss(id: string) {
    setError("");
    try { await api(`/api/v1/agent/proposals/${id}/dismiss`, { method: "POST" }); await load(); }
    catch (e: any) { setError(e.message); }
  }
  async function draft(id: string) {
    setDraftingId(id); setError(""); setNotice("");
    try {
      await api(`/api/v1/agent/proposals/${id}/draft`, { method: "POST" });
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setDraftingId(""); }
  }
  async function saveSchedule() {
    setAction("schedule"); setError(""); setNotice("");
    try {
      const saved = await api<Schedule>("/api/v1/agent/schedule", {
        method: "PUT", body: JSON.stringify(schedule),
      });
      setSchedule(saved); setCurrentSchedule(saved); setNotice(saved.enabled ? "Automatic scans enabled." : "Automatic scans paused.");
    } catch (e: any) { setError(e.message); }
    finally { setAction(null); }
  }
  async function approve(p: Proposal, e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const draft = p.evidence?.draft;
    if (!draft || p.draft_stale) return;
    const fields = new FormData(e.currentTarget);
    setAction("approve"); setError(""); setNotice("");
    try {
      await api(`/api/v1/agent/proposals/${p.id}/approve`, { method: "POST", body: JSON.stringify({
        source_updated_at: Object.fromEntries(draft.source_memory_ids.map((id, i) => [id, draft.source_updated_at[i]])),
        title: fields.get("title"), content: fields.get("content"),
      }) });
      setNotice("Reviewed summary saved with source links. Both original memories are unchanged.");
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setAction(null); }
  }
  const lastScan = runs[0];
  const automaticScans = currentSchedule.enabled;

  return <div className={styles.page}>
    <Topbar eyebrow="Memory maintenance" title="Memory Agent" />
    <section className={styles.overview} aria-label="Agent overview">
      <div className={styles.overviewHeader}>
        <p>Find duplicates, conflicts and stale memories. Review each suggestion before making changes.</p>
        <button className="button primary" disabled={busy} onClick={scan}>
          {action === "scan" ? "Scanning…" : "Scan project"}
        </button>
      </div>
      <dl className={styles.metrics}>
        <div><dt>Pending proposals</dt><dd>{loaded ? proposals.length : "—"}</dd></div>
        <div><dt>Last scan</dt><dd>{loaded ? dateText(lastScan?.created_at) : "—"}</dd></div>
        <div><dt>Automatic scans</dt><dd>{loaded ? automaticScans ? "On" : "Off" : "—"}</dd></div>
      </dl>
    </section>
    {error && <div className="errorBox" role="alert">{error}</div>}
    {notice && <div className="successBox" role="status">{notice}</div>}

    <div className={styles.views} role="group" aria-label="Memory Agent views">
      {views.map(([id, label]) => (
        <button key={id} type="button" aria-controls={`agent-${id}`} aria-pressed={view === id} onClick={() => setView(id)}>
          {label}
        </button>
      ))}
    </div>

    <section id="agent-review" className="panel" hidden={view !== "review"} aria-labelledby="agent-review-title">
      <div className="panelHead"><h2 id="agent-review-title">Review queue</h2></div>
      {!loaded && !error && <p className="empty" role="status">Loading proposals…</p>}
      {loaded && proposals.length === 0 && (
        <div className={styles.empty}>
          <strong>No proposals to review</strong>
          <p>{lastScan ? "New suggestions will appear here after a scan." : "Run a scan to check this project for suggestions."}</p>
        </div>
      )}
      {proposals.map(p => <article className={styles.proposal} key={p.id}>
        <div className={styles.proposalMeta}>
          <span className="badge pending">{p.proposal_type.replaceAll("_", " ")}</span>
          <time dateTime={p.created_at}>{dateText(p.created_at)}</time>
        </div>
        <h3><Link href={`/memories/${p.memory_id}`}>{p.memory_title}</Link></h3>
        {p.related_memory_id && <p className={styles.related}>Related memory <Link href={`/memories/${p.related_memory_id}`}>{p.related_title || "Open source"}</Link></p>}
        <p>{p.reason}</p>
        <div className={styles.actions}>
          {p.proposal_type === "duplicate" && (
            <button className="button" disabled={!!draftingId || busy} onClick={() => draft(p.id)}>
              {draftingId === p.id ? "Drafting…" : p.evidence?.draft ? "Regenerate draft" : "Draft consolidation"}
            </button>
          )}
          <button className="ghostButton" disabled={busy || draftingId === p.id} onClick={() => dismiss(p.id)}>Dismiss</button>
        </div>
        {p.evidence?.draft && <div className={styles.draft}>
          <strong>{p.evidence.draft.safe_to_merge ? p.evidence.draft.title : "Keep these separate"}</strong>
          <p className="meta">AI suggestion for review. Check the source memories before using it.</p>
          {p.draft_stale && <p className="errorBox">A source memory changed since this draft. Generate it again before using it.</p>}
          {p.evidence.draft.quotes?.map(quote => <blockquote key={quote.source}>
            <p>{quote.quote}</p><Link href={`/memories/${p.evidence!.draft!.source_memory_ids[quote.source - 1]}`}>Source {quote.source}</Link>
          </blockquote>)}
          {p.evidence.draft.safe_to_merge && p.evidence.draft.quotes?.length === 2 && !p.draft_stale && <form
            className={styles.form} key={JSON.stringify([p.evidence.draft.source_updated_at,p.evidence.draft.content])} onSubmit={e => approve(p, e)}>
            <div className="field"><label htmlFor={`summary-title-${p.id}`}>Reviewed summary title</label>
              <input id={`summary-title-${p.id}`} className="input" name="title" defaultValue={p.evidence.draft.title} required maxLength={300} /></div>
            <div className="field"><label htmlFor={`summary-content-${p.id}`}>Reviewed summary</label>
              <textarea id={`summary-content-${p.id}`} className="textarea" name="content" defaultValue={p.evidence.draft.content} required maxLength={10000} /></div>
            <label><input type="checkbox" required /> I checked both sources and reviewed this summary.</label>
            <button className="button primary" disabled={busy}>Save reviewed consolidation</button>
          </form>}
          <p>{p.evidence.draft.reason}</p>
          {p.evidence.draft.content && !p.draft_stale && <button className="ghostButton" onClick={() => navigator.clipboard.writeText(`${p.evidence?.draft?.title}\n\n${p.evidence?.draft?.content}`).then(() => setNotice("Draft copied for review.")).catch(() => setError("Could not copy draft."))}>Copy draft</button>}
        </div>}
      </article>)}
    </section>

    <div id="agent-consolidate" className={styles.tools} hidden={view !== "consolidate"}><ClusterConsolidation /></div>

    <div id="agent-activity" hidden={view !== "activity"}>
      <div className={styles.activity}>
        <section className="panel">
          <div className="panelHead"><h2>Recent scans</h2></div>
          {!loaded && !error && <p className="empty" role="status">Loading scan history…</p>}
          {loaded && !runs.length && <div className="empty">No scans yet.</div>}
          {runs.map(run => (
            <div className={styles.run} key={run.id}>
              <div className={styles.proposalMeta}>
                <strong>{run.trigger_type === "scheduled" ? "Automatic" : "Manual"} scan</strong>
                <span className={`badge ${run.status === "completed" ? "ready" : run.status}`}>{run.status}</span>
              </div>
              <time className="meta" dateTime={run.created_at}>{dateText(run.created_at)}</time>
              {run.result && <span>{run.result.total} new {run.result.total === 1 ? "proposal" : "proposals"}</span>}
              {run.error_message && <p className="errorBox">{run.error_message}</p>}
            </div>
          ))}
        </section>
        <section className="panel">
          <div className="panelHead"><h2>Automatic scans</h2></div>
          {currentSchedule.enabled && <p className="meta">Next scan {dateText(currentSchedule.next_scan_at)}</p>}
          {isAdmin && <form className={styles.form} onSubmit={e => { e.preventDefault(); void saveSchedule(); }}>
            <label className="field"><span>Frequency</span>
              <select className="select" value={schedule.interval_hours} onChange={e => setSchedule({ ...schedule, interval_hours: Number(e.target.value) })}>
                <option value={24}>Daily</option><option value={72}>Every 3 days</option><option value={168}>Weekly</option>
              </select>
            </label>
            <label className="field"><span>Automatic scans</span>
              <select className="select" value={schedule.enabled ? "on" : "off"} onChange={e => setSchedule({ ...schedule, enabled: e.target.value === "on" })}>
                <option value="off">Off</option><option value="on">On</option>
              </select>
            </label>
            <button className="button" disabled={busy}>{action === "schedule" ? "Saving…" : "Save schedule"}</button>
          </form>}
          {loaded && !isAdmin && <p className="meta">Only a project administrator can change the schedule.</p>}
        </section>
      </div>
    </div>

    <div id="agent-history" className={styles.tools} hidden={view !== "history"}><LifecycleHistory /></div>
  </div>;
}
