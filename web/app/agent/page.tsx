"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

type Draft = { safe_to_merge: boolean; title?: string; content?: string; reason: string };
type Proposal = { id: string; proposal_type: string; memory_id: string; memory_title: string; related_memory_id?: string; related_title?: string; reason: string; created_at: string; evidence?: { draft?: Draft }; draft_stale?: boolean };
type ScanRun = { id: string; trigger_type: string; status: string; result?: { total: number }; error_message?: string; created_at: string };
type Schedule = { enabled: boolean; interval_hours: number; next_scan_at?: string | null };

export default function AgentPage() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [runs, setRuns] = useState<ScanRun[]>([]);
  const [schedule, setSchedule] = useState<Schedule>({ enabled: false, interval_hours: 24 });
  const [isAdmin, setIsAdmin] = useState(false);
  const [busy, setBusy] = useState(false);
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
      setProposals(items); setRuns(history); setSchedule(current); setIsAdmin(me.is_admin);
    }
    catch (e: any) { setError(e.message); }
  }
  useEffect(() => { void load(); }, []);
  async function scan() {
    setBusy(true); setError("");
    try {
      const result = await api<{ total: number }>("/api/v1/agent/scan", { method: "POST" });
      setNotice(`${result.total} new proposal${result.total === 1 ? "" : "s"}.`);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
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
    setBusy(true); setError(""); setNotice("");
    try {
      const saved = await api<Schedule>("/api/v1/agent/schedule", {
        method: "PUT", body: JSON.stringify(schedule),
      });
      setSchedule(saved); setNotice(saved.enabled ? "Automatic scans enabled." : "Automatic scans paused.");
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <>
    <Topbar eyebrow="Human reviewed maintenance" title="Memory Agent" />
    <p className="meta">Scans for likely duplicates, import conflicts, stale facts, low confidence and missing provenance. It never changes memories.</p>
    <button className="button primary" disabled={busy} onClick={scan}>{busy ? "Scanning…" : "Scan this project"}</button>
    {error && <div className="errorBox">{error}</div>}{notice && <div className="successBox">{notice}</div>}
    <section className="panel"><div className="panelHead"><h2>Automatic scans</h2></div>
      <p className="meta">Off by default. Scans add suggestions for review and never change memories.</p>
      {isAdmin && <div className="row">
        <label className="field"><span>Frequency</span><select className="select" value={schedule.interval_hours} onChange={e => setSchedule({ ...schedule, interval_hours: Number(e.target.value) })}>
          <option value={24}>Daily</option><option value={72}>Every 3 days</option><option value={168}>Weekly</option>
        </select></label>
        <label className="field"><span>Automatic scans</span><select className="select" value={schedule.enabled ? "on" : "off"} onChange={e => setSchedule({ ...schedule, enabled: e.target.value === "on" })}>
          <option value="off">Off</option><option value="on">On</option>
        </select></label>
        <button className="button primary" disabled={busy} onClick={saveSchedule}>Save schedule</button>
      </div>}
      {schedule.enabled && <p className="meta">Next scan: {dateText(schedule.next_scan_at)}</p>}
    </section>
    <section className="panel"><div className="panelHead"><h2>Recent scans</h2></div>
      {!runs.length && <div className="empty">No scans yet.</div>}
      {runs.map(run => <div className="healthMemory" key={run.id}>
        <strong>{run.trigger_type === "scheduled" ? "Automatic" : "Manual"} scan</strong>
        <span className={`badge ${run.status}`}>{run.status}</span>
        <span className="meta">{dateText(run.created_at)}</span>
        {run.result && <span>{run.result.total} new proposals</span>}
        {run.error_message && <span>{run.error_message}</span>}
      </div>)}
    </section>
    <section className="panel"><div className="panelHead"><h2>Proposals</h2><span className="meta">{proposals.length} pending</span></div>
      {!proposals.length && <div className="empty">No pending proposals.</div>}
      {proposals.map(p => <div className="healthMemory" key={p.id}>
        <span className="badge pending">{p.proposal_type.replace("_", " ")}</span>
        <Link href={`/memories/${p.memory_id}`}><strong>{p.memory_title}</strong></Link>
        {p.related_memory_id && <Link href={`/memories/${p.related_memory_id}`}>{p.related_title}</Link>}
        <span>{p.reason}</span><span className="meta">{dateText(p.created_at)}</span>
        {p.proposal_type === "duplicate" && <button className="ghostButton" disabled={draftingId === p.id} onClick={() => draft(p.id)}>{draftingId === p.id ? "Drafting…" : "Draft consolidation"}</button>}
        {p.evidence?.draft && <div className="panel" style={{ width: "100%", marginTop: 8 }}>
          <strong>{p.evidence.draft.safe_to_merge ? p.evidence.draft.title : "Keep these separate"}</strong>
          <p className="meta">AI suggestion for review. Check the source memories before using it.</p>
          {p.draft_stale && <p className="errorBox">A source memory changed since this draft. Generate it again before using it.</p>}
          {p.evidence.draft.content && <p style={{ whiteSpace: "pre-wrap" }}>{p.evidence.draft.content}</p>}
          <p>{p.evidence.draft.reason}</p>
          {p.evidence.draft.content && !p.draft_stale && <button className="ghostButton" onClick={() => navigator.clipboard.writeText(`${p.evidence?.draft?.title}\n\n${p.evidence?.draft?.content}`).then(() => setNotice("Draft copied for review.")).catch(() => setError("Could not copy draft."))}>Copy draft</button>}
        </div>}
        <button className="ghostButton" onClick={() => dismiss(p.id)}>Dismiss</button>
      </div>)}
    </section>
  </>;
}
