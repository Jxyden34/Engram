"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { api, dateText } from "@/lib/api";

type Budget = "quick" | "standard" | "deep";
type Claim = { text: string; citations: { source: number; quote: string }[] };
type Source = { number: number; id: string; kind?: "memory" | "document_chunk"; document_id?: string | null; title: string; version?: string; content?: string; status?: string };
type Answer = { question: string; budget: Budget; include_documents?: boolean; project_revision?: string; claims: Claim[]; sources: Source[]; insufficient?: boolean; evidence_chars?: number; status?: string; evidence_changed?: boolean; title?: string; refresh_of?: string | null; refresh_title?: string; changes?: {available:boolean;added?:string[];removed?:string[];unchanged?:number;redacted?:number;sources?:{title:string;state:string}[];basis?:string} | null };
type Brief = { id: string; title: string; created_at: string };

export default function ReflectionPanel() {
  const [question, setQuestion] = useState("");
  const [budget, setBudget] = useState<Budget>("standard");
  const [includeDocuments, setIncludeDocuments] = useState(false);
  const sourceLink = (source: Source) => source.kind === 'document_chunk' ? `/documents#document-${source.document_id}` : `/memories/${source.id}`;
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [title, setTitle] = useState("");
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [selected, setSelected] = useState<Brief | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadBriefs() {
    setBriefs(await api<Brief[]>("/api/v1/intelligence/briefs"));
  }
  useEffect(() => { loadBriefs().catch(e => setError(e.message)); }, []);

  async function generate(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(""); setNotice(""); setAnswer(null); setSelected(null);
    try {
      setAnswer(await api<Answer>("/api/v1/intelligence/reflect", { method: "POST", body: JSON.stringify({ question, budget,include_documents:includeDocuments }) }));
      setTitle(question.slice(0, 120));
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!answer) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const saved = await api<Brief>("/api/v1/intelligence/briefs", { method: "POST", body: JSON.stringify({
        title, question: answer.question, budget: answer.budget, project_revision: answer.project_revision,
        sources: answer.sources.map(({ id, version,kind }) => ({ id, version,kind:kind||'memory' })), claims: answer.claims,
        include_documents:!!answer.include_documents,
        refresh_of: answer.refresh_of || null,
      }) });
      await loadBriefs(); setSelected(saved); setNotice("Brief saved. Your original memories are unchanged.");
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function open(brief: Brief) {
    setBusy(true); setError(""); setNotice(""); setAnswer(null); setSelected(null);
    try {
      const next = await api<Answer>(`/api/v1/intelligence/briefs/${brief.id}`);
      setAnswer(next); setSelected({ ...brief, title: next.title || brief.title }); setQuestion(next.question); setBudget(next.budget);
      setIncludeDocuments(!!next.include_documents);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      await api(`/api/v1/intelligence/briefs/${selected.id}`, { method: "DELETE" });
      setAnswer(null); setSelected(null); await loadBriefs(); setNotice("Saved brief deleted. Source memories are unchanged.");
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function refresh() {
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const next = await api<Answer>(`/api/v1/intelligence/briefs/${selected.id}/refresh`, { method: "POST" });
      setAnswer(next); setTitle(next.refresh_title || selected.title); setSelected(null);
      setQuestion(next.question); setBudget(next.budget);
      setIncludeDocuments(!!next.include_documents);
      setNotice("Fresh preview ready. Review the evidence and save a new brief; the previous snapshot is unchanged.");
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  return <section className="panel" aria-labelledby="reflection-heading">
    <div className="panelHead"><h2 id="reflection-heading">Reflect &amp; project briefs</h2></div>
    <p className="meta">Bring current memories together into an answer with checkable excerpts. Save useful answers as project briefs after reviewing them.</p>
    <form onSubmit={generate}>
      <div className="field"><label htmlFor="reflection-question">Question</label>
        <textarea id="reflection-question" className="textarea" value={question} onChange={e => setQuestion(e.target.value)} maxLength={1000} required placeholder="What decisions and constraints should guide this project?" /></div>
      <div className="field"><label htmlFor="reflection-budget">Evidence budget</label>
        <select id="reflection-budget" className="select" value={budget} onChange={e => setBudget(e.target.value as Budget)}>
          <option value="quick">Quick · up to 6 sources</option>
          <option value="standard">Standard · up to 12 sources</option>
          <option value="deep">Deep · up to 20 sources</option>
        </select></div>
      <label><input type="checkbox" checked={includeDocuments} onChange={e=>setIncludeDocuments(e.target.checked)} /> Include document evidence</label>
      <button className="button primary" disabled={busy || !question.trim()}>{busy ? "Working…" : "Reflect"}</button>
    </form>
    {error && <div className="errorBox" role="alert">{error}</div>}
    {notice && <div className="successBox" role="status">{notice}</div>}
    {answer && <div aria-live="polite">
      <h3>{selected?.title || "Review this answer"}</h3>
      <p className="meta">{answer.sources.length} retrieved sources · {answer.budget} budget. Quotes are checked against source text; review whether they support each conclusion.</p>
      {answer.status === "needs_review" && <p role="status" className="errorBox">Project memories have changed. {answer.evidence_changed ? "Supporting evidence changed or became unavailable, so the old answer is hidden." : "New or changed memories may affect this brief."} Rebuild and review before relying on it.</p>}
      {answer.insufficient && <p>No supported answer was found in the retrieved evidence. Try a more specific question or use Search.</p>}
      {answer.changes && <details open><summary>What changed?</summary>
        {!answer.changes.available ? <p>The previous brief is no longer available.</p> : <>
          <p className="meta">{answer.changes.basis}</p>
          <h4>Added to this answer</h4>{answer.changes.added?.map((text,i)=><p key={i}>{text}</p>)}
          <h4>Not in this answer</h4>{answer.changes.removed?.map((text,i)=><p key={i}>{text}</p>)}
          <p className="meta">{answer.changes.unchanged} unchanged statements. {answer.changes.redacted ? `${answer.changes.redacted} statements hidden because supporting sources are unavailable.` : ""}</p>
          {answer.changes.sources?.map((source,i)=><p key={i}>{source.title} · {source.state}</p>)}
        </>}
      </details>}
      {answer.claims.map((claim, index) => <div key={index} style={{ borderTop: "1px solid #2a3037", padding: "12px 0" }}>
        <p>{claim.text}</p>
        {claim.citations.map((citation, i) => {
          const source = answer.sources[citation.source - 1];
          return <blockquote key={i}><p>{citation.quote}</p>{source && <Link href={sourceLink(source)}>[{citation.source}] {source.title}</Link>}</blockquote>;
        })}
      </div>)}
      <details><summary>Retrieved evidence</summary>{answer.sources.map(source => <div key={source.id}>
        <p>{source.status === "unavailable" ? `[${source.number}] Unavailable source` : <Link href={sourceLink(source)}>[{source.number}] {source.title}</Link>} {source.status && `· ${source.status}`}</p>
        {source.content && <p style={{ whiteSpace: "pre-wrap" }}>{source.content}</p>}
      </div>)}</details>
      {!selected && !!answer.claims.length && !answer.insufficient && <form onSubmit={save}>
        <div className="field"><label htmlFor="brief-title">Brief title</label><input id="brief-title" className="input" value={title} onChange={e => setTitle(e.target.value)} maxLength={120} required /></div>
        <button className="button" disabled={busy || !title.trim()}>Save reviewed brief</button>
      </form>}
      {answer.refresh_of && <p className="meta">Refreshed from an earlier brief. <button className="ghostButton" disabled={busy} onClick={() => open({id:answer.refresh_of!,title:"Previous brief",created_at:""})}>Open previous brief</button></p>}
      {selected && <div className="row"><button className="button" disabled={busy} onClick={refresh}>Refresh for review</button><button className="ghostButton" disabled={busy} onClick={remove}>Delete saved brief</button></div>}
    </div>}
    <h3>Saved project briefs</h3>
    <p className="meta">Rebuilding creates a new preview. Save it as a new brief after review; existing briefs stay unchanged.</p>
    {!briefs.length && <p className="empty">No saved briefs in this project.</p>}
    {briefs.map(brief => <div key={brief.id} className="row" style={{ justifyContent: "space-between", marginTop: 8 }}>
      <button className="ghostButton" disabled={busy} onClick={() => open(brief)}>{brief.title}</button>
      <span className="meta">{dateText(brief.created_at)}</span>
    </div>)}
  </section>;
}
