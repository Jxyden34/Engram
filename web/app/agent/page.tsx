"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

type Proposal = { id: string; proposal_type: string; memory_id: string; memory_title: string; related_memory_id?: string; related_title?: string; reason: string; created_at: string };

export default function AgentPage() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function load() {
    try { setProposals(await api<Proposal[]>("/api/v1/agent/proposals")); }
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
  return <>
    <Topbar eyebrow="Human reviewed maintenance" title="Memory Agent" />
    <p className="meta">Scans for likely duplicates, conflicts, stale facts and missing provenance. It never changes memories.</p>
    <button className="button primary" disabled={busy} onClick={scan}>{busy ? "Scanning…" : "Scan this project"}</button>
    {error && <div className="errorBox">{error}</div>}{notice && <div className="successBox">{notice}</div>}
    <section className="panel"><div className="panelHead"><h2>Proposals</h2><span className="meta">{proposals.length} pending</span></div>
      {!proposals.length && <div className="empty">No pending proposals.</div>}
      {proposals.map(p => <div className="healthMemory" key={p.id}>
        <span className="badge pending">{p.proposal_type.replace("_", " ")}</span>
        <Link href={`/memories/${p.memory_id}`}><strong>{p.memory_title}</strong></Link>
        {p.related_memory_id && <Link href={`/memories/${p.related_memory_id}`}>{p.related_title}</Link>}
        <span>{p.reason}</span><span className="meta">{dateText(p.created_at)}</span>
        <button className="ghostButton" onClick={() => dismiss(p.id)}>Dismiss</button>
      </div>)}
    </section>
  </>;
}
