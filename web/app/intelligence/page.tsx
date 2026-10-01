"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

type Plan = { intent: string; include_historical: boolean; strategy: string };
type Context = { plan: Plan; context: string; estimated_tokens: number; items: { id: string; title: string; source: string; truncated: boolean }[]; matches: any[] };
type Memory = { id: string; title: string; content: string; confidence: number; source_trust: number; source_type: string; source_ref?: string | null; updated_at: string; valid_from?: string | null; valid_to?: string | null };
type Pair = { first_id: string; first_title: string; second_id: string; second_title: string; similarity: number };
type Comparison = { first: Memory; second: Memory; recommended_current_id: string; basis: string };

export default function IntelligencePage() {
  const [query, setQuery] = useState("");
  const [context, setContext] = useState<Context | null>(null);
  const [results, setResults] = useState<any[]>([]);
  const [pairs, setPairs] = useState<Pair[] | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [currentId, setCurrentId] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function retrieve(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!query.trim()) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const nextContext = await api<Context>("/api/v1/intelligence/context", { method: "POST", body: JSON.stringify({ query, max_chars: 6000 }) });
      setContext(nextContext); setResults(nextContext.matches);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function loadPairs() {
    setBusy(true); setError("");
    try { setPairs(await api<Pair[]>("/api/v1/intelligence/conflict-candidates")); }
    catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function compare(pair: Pair) {
    setBusy(true); setError(""); setComparison(null); setCurrentId(""); setReason("");
    try {
      setComparison(await api<Comparison>("/api/v1/intelligence/compare", {
        method: "POST", body: JSON.stringify({ first_id: pair.first_id, second_id: pair.second_id }),
      }));
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function resolve(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!comparison || !currentId || reason.trim().length < 10) return;
    setBusy(true); setError("");
    try {
      await api("/api/v1/intelligence/resolve", {
        method: "POST", body: JSON.stringify({ first_id: comparison.first.id, second_id: comparison.second.id, current_id: currentId, reason }),
      });
      setNotice("Resolution saved. Both memories remain available; the other fact is now historical.");
      setComparison(null); setPairs(null); setCurrentId(""); setReason("");
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  return <>
    <Topbar eyebrow="Memory intelligence" title="Find the right context" />
    {error && <div className="errorBox">{error}</div>}
    {notice && <div className="successBox">{notice}</div>}
    <section className="panel">
      <div className="panelHead"><h2>Context builder</h2><span className="meta">No generated answer</span></div>
      <p className="meta">Search blends meaning, exact words, entity links, time and source quality. The preview keeps source labels so you can check each fact.</p>
      <form className="searchBar" onSubmit={retrieve}>
        <input className="input" value={query} onChange={e => setQuery(e.target.value)} placeholder="What context do you need?" maxLength={5000} />
        <button className="button primary" disabled={busy || !query.trim()}>{busy ? "Working…" : "Build context"}</button>
      </form>
      {context && <>
        <p className="meta">Plan: <strong>{context.plan.intent}</strong> · {context.items.length} sources · about {context.estimated_tokens} tokens</p>
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 440, overflow: "auto", padding: 16, background: "#111317", borderRadius: 12 }}>{context.context}</pre>
        <button className="ghostButton" onClick={async () => { await navigator.clipboard.writeText(context.context); setNotice("Context copied with source labels."); }}>Copy context</button>
      </>}
    </section>
    {context && <section className="panel">
      <div className="panelHead"><h2>Why these memories?</h2><span className="meta">ranked evidence</span></div>
      {results.map((item) => <div key={item.id} style={{ borderTop: "1px solid #2a3037", padding: "14px 0" }}>
        <Link href={`/memories/${item.id}`}><strong>{item.title}</strong></Link>
        <div className="meta">{item.temporal_state} · score {Number(item.retrieval_score).toFixed(3)} · {(item.match_reasons || []).join(" · ") || "semantic candidate"}</div>
        <div className="meta">{item.source_type}{item.source_ref ? `: ${item.source_ref}` : ""}</div>
      </div>)}
      {!results.length && <div className="empty">No matching memories yet.</div>}
    </section>}
    <section className="panel">
      <div className="panelHead"><h2>Potential contradictions</h2><button className="ghostButton" onClick={loadPairs} disabled={busy}>Find pairs to review</button></div>
      <p className="meta">Similar memories can be duplicates, compatible facts, or contradictions. Compare the evidence before choosing which fact is current.</p>
      {pairs?.map((pair) => <div key={`${pair.first_id}-${pair.second_id}`} className="healthPair">
        <span>{pair.first_title} ↔ {pair.second_title}</span>
        <span>{Math.round(pair.similarity * 100)}% similar</span>
        <button className="ghostButton" onClick={() => compare(pair)} disabled={busy}>Compare</button>
      </div>)}
      {pairs && !pairs.length && <div className="empty">No strong similarity pairs found.</div>}
      <p className="meta"><Link href="/imports">Memory Inbox</Link> also lists conflicts found during imports.</p>
    </section>
    {comparison && <section className="panel">
      <div className="panelHead"><h2>Review both facts</h2><span className="meta">No automatic deletion</span></div>
      <p className="meta">Suggested current: {comparison.recommended_current_id === comparison.first.id ? comparison.first.title : comparison.second.title}. {comparison.basis}</p>
      <form onSubmit={resolve}>
        <div className="split">{[comparison.first, comparison.second].map(item => <label className="panel" key={item.id} style={{ display: "block", cursor: "pointer" }}>
          <input type="radio" name="current" checked={currentId === item.id} onChange={() => setCurrentId(item.id)} /> Keep current: <strong>{item.title}</strong>
          <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{item.content}</p>
          <div className="meta">Confidence {Number(item.confidence).toFixed(2)} · source trust {Number(item.source_trust).toFixed(2)} · {item.source_type}{item.source_ref ? `: ${item.source_ref}` : ""} · updated {dateText(item.updated_at)}</div>
          <Link href={`/memories/${item.id}`}>Open full memory</Link>
        </label>)}</div>
        <div className="field full"><label>Why is this the current fact?</label><textarea className="textarea" value={reason} onChange={e => setReason(e.target.value)} minLength={10} maxLength={1000} required /></div>
        <div className="row" style={{ justifyContent: "flex-end", marginTop: 12 }}><button className="button primary" disabled={busy || !currentId || reason.trim().length < 10}>Save reviewed resolution</button></div>
      </form>
    </section>}
  </>;
}
