"use client";

import { FormEvent, useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

type Candidate = Record<string, any> & { origin: "document" | "chatgpt" };

const comparisonNames: Record<string, string> = {
  new: "New memory",
  duplicate: "Possible duplicate",
  related: "Related memory",
  updates: "Possible update",
  conflicts: "Conflict to review",
};
const comparisonOrder = ["conflicts", "updates", "duplicate", "related", "new"];

export default function MemoryInboxPage() {
  const [status, setStatus] = useState("pending");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [documents, setDocuments] = useState<any[]>([]);
  const [chatDocuments, setChatDocuments] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [chatJobs, setChatJobs] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState("");
  const [editing, setEditing] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load(nextStatus = status) {
    try {
      const [docCandidates, chatCandidates, sourceDocs, sourceJobs, eligibleChatDocs, imports] = await Promise.all([
        api<any[]>(`/api/v1/imports/documents/candidates?status=${nextStatus}&limit=300`),
        api<any[]>(`/api/v1/imports/chatgpt/candidates?status=${nextStatus}&limit=200`),
        api<any[]>("/api/v1/imports/documents/sources"),
        api<any[]>("/api/v1/imports/documents/jobs"),
        api<any[]>("/api/v1/imports/chatgpt/documents"),
        api<any[]>("/api/v1/imports/chatgpt/jobs"),
      ]);
      const combined = [
        ...docCandidates.map((item) => ({ ...item, origin: "document" as const })),
        ...chatCandidates.map((item) => ({ ...item, origin: "chatgpt" as const })),
      ];
      combined.sort((a, b) => {
        const order = comparisonOrder.indexOf(a.comparison) - comparisonOrder.indexOf(b.comparison);
        if (order) return order;
        return Number(b.confidence || 0) - Number(a.confidence || 0);
      });
      setCandidates(combined);
      setDocuments(sourceDocs);
      setJobs(sourceJobs);
      setChatDocuments(eligibleChatDocs);
      setChatJobs(imports);
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 12000);
    return () => clearInterval(timer);
  }, [status]);

  async function review(candidate: Candidate, action: "accept" | "reject") {
    const key = `${candidate.origin}:${candidate.id}`;
    setActive(key);
    setError("");
    setNotice("");
    const prefix = candidate.origin === "chatgpt" ? "chatgpt" : "documents";
    try {
      await api(`/api/v1/imports/${prefix}/candidates/${candidate.id}/${action}`, { method: "POST" });
      setNotice(action === "accept" ? "Memory accepted." : "Suggestion rejected.");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActive("");
    }
  }

  async function saveCandidate(e: FormEvent<HTMLFormElement>, candidate: Candidate) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const prefix = candidate.origin === "chatgpt" ? "chatgpt" : "documents";
    setActive(`${candidate.origin}:${candidate.id}`);
    try {
      await api(`/api/v1/imports/${prefix}/candidates/${candidate.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: f.get("title"),
          content: f.get("content"),
          memory_type: f.get("memory_type"),
          importance: Number(f.get("importance")),
          confidence: Number(f.get("confidence")),
          tags: String(f.get("tags") || "").split(",").map((value) => value.trim()).filter(Boolean),
        }),
      });
      setEditing("");
      setNotice("Suggestion updated and rechecked against your memories.");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActive("");
    }
  }

  async function analyzeDocument(id: string, isChatExport = false) {
    const key = `${isChatExport ? "chatgpt" : "document"}:${id}`;
    setActive(key);
    setError("");
    setNotice("");
    try {
      if (isChatExport) {
        await api("/api/v1/imports/chatgpt/jobs", {
          method: "POST",
          body: JSON.stringify({ source_document_id: id }),
        });
      } else {
        await api(`/api/v1/imports/documents/jobs/${id}`, { method: "POST" });
      }
      setNotice("Analysis queued. Suggestions will appear here when processing finishes.");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActive("");
    }
  }

  async function analyzeAll() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result: any = await api("/api/v1/imports/documents/analyse-all", { method: "POST" });
      setNotice(`Queued ${result.queued} document${result.queued === 1 ? "" : "s"}; skipped ${result.skipped}; errors ${result.errors}.`);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Topbar eyebrow="Review before remembering" title="Memory Inbox" />
      {error && <div className="errorBox">{error}</div>}
      {notice && <div className="successBox">{notice}</div>}

      <section className="panel" style={{ marginTop: 0 }}>
        <div className="panelHead">
          <div>
            <h2>Source documents</h2>
            <div className="meta">Analyze ready documents to suggest durable memories. Nothing is added to your memory until you accept it.</div>
          </div>
          <button className="button primary" onClick={analyzeAll} disabled={busy || documents.length === 0}>
            {busy ? "Queueing…" : "Analyze all ready documents"}
          </button>
        </div>
        {documents.length ? documents.slice(0, 8).map((doc) => (
          <div className="importSource" key={doc.id}>
            <div>
              <strong>{doc.filename}</strong>
              <div className="meta">Added {dateText(doc.created_at)} · {doc.pending_candidates || 0} pending suggestion{Number(doc.pending_candidates) === 1 ? "" : "s"}</div>
            </div>
            <div className="row">
              <span className="badge">{doc.latest_analysis_status || "ready"}</span>
              <button className="ghostButton" disabled={Boolean(active) || Number(doc.pending_candidates) > 0}
                onClick={() => void analyzeDocument(doc.id)}>
                {active === `document:${doc.id}` ? "Queueing…" : "Analyze"}
              </button>
            </div>
          </div>
        )) : <div className="empty">No ready source documents yet. Add documents or connect a source from the Documents or Connectors pages.</div>}
      </section>

      <section className="panel">
        <div className="panelHead">
          <div>
            <h2>ChatGPT exports</h2>
            <div className="meta">Import a ChatGPT conversation export to extract reviewable memories.</div>
          </div>
        </div>
        {chatDocuments.length ? chatDocuments.slice(0, 8).map((doc) => (
          <div className="importSource" key={doc.id}>
            <div>
              <strong>{doc.filename}</strong>
              <div className="meta">Added {dateText(doc.created_at)} · {doc.latest_import_status || doc.status}</div>
            </div>
            <button className="ghostButton" disabled={Boolean(active) || ["queued", "processing", "ready"].includes(doc.latest_import_status)}
              onClick={() => void analyzeDocument(doc.id, true)}>
              {active === `chatgpt:${doc.id}` ? "Queueing…" : "Import conversations"}
            </button>
          </div>
        )) : <div className="empty">No ChatGPT conversation exports found. Upload an export from the Documents page.</div>}
      </section>

      <section className="panel">
        <div className="panelHead">
          <div>
            <h2>Suggested memories</h2>
            <div className="meta">Compare every suggestion with existing memories before accepting it.</div>
          </div>
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Candidate status">
            <option value="pending">Needs review</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
        <div className="candidateLegend">
          <span><i className="dot conflict" /> Conflict</span>
          <span><i className="dot update" /> Update</span>
          <span><i className="dot duplicate" /> Duplicate</span>
          <span><i className="dot related" /> Related</span>
          <span><i className="dot fresh" /> New</span>
        </div>
        {candidates.length ? <div className="candidateGrid">
          {candidates.map((candidate) => {
            const key = `${candidate.origin}:${candidate.id}`;
            const prefix = candidate.comparison || "new";
            return <article className={`candidateCard ${prefix}`} key={key}>
              <div className="candidateHead">
                <div>
                  <span className={`badge compare-${prefix}`}>{comparisonNames[prefix] || prefix}</span>
                  <h3>{candidate.title}</h3>
                </div>
                <div className="candidateScore">{Math.round(Number(candidate.confidence || 0) * 100)}%<span>confidence</span></div>
              </div>
              <p>{candidate.content}</p>
              <div className="meta">{candidate.memory_type} · importance {candidate.importance}/10 · {candidate.origin === "chatgpt" ? candidate.conversation_title || candidate.source_filename : candidate.source_filename}</div>
              {candidate.source_excerpt && <blockquote className="sourceExcerpt">{candidate.source_excerpt}</blockquote>}
              {candidate.nearest_memory_title && <div className="comparisonBox">
                <span className="meta">Closest existing memory{candidate.nearest_similarity != null ? ` · ${Math.round(Number(candidate.nearest_similarity) * 100)}% similarity` : ""}</span>
                <strong>{candidate.nearest_memory_title}</strong>
                {candidate.nearest_memory_content && <p>{candidate.nearest_memory_content}</p>}
              </div>}
              <div className="meta">Source: {candidate.origin === "chatgpt" ? "ChatGPT export" : "document analysis"} · {dateText(candidate.created_at)}</div>
              {status === "pending" && editing === key && <form className="formGrid" onSubmit={(e) => void saveCandidate(e, candidate)}>
                <div className="field full"><label>Title</label><input className="input" name="title" defaultValue={candidate.title} required /></div>
                <div className="field full"><label>Content</label><textarea className="textarea" name="content" defaultValue={candidate.content} required /></div>
                <div className="field"><label>Type</label><input className="input" name="memory_type" defaultValue={candidate.memory_type} /></div>
                <div className="field"><label>Importance</label><input className="input" type="number" name="importance" min="1" max="10" defaultValue={candidate.importance} /></div>
                <div className="field"><label>Confidence</label><input className="input" type="number" name="confidence" min="0" max="1" step="0.01" defaultValue={candidate.confidence} /></div>
                <div className="field"><label>Tags</label><input className="input" name="tags" defaultValue={(candidate.tags || []).join(", ")} /></div>
                <div className="field full row" style={{ justifyContent: "flex-end" }}>
                  <button type="button" className="ghostButton" onClick={() => setEditing("")}>Cancel</button>
                  <button className="button primary" disabled={active === key}>Save changes</button>
                </div>
              </form>}
              {status === "pending" && editing !== key && <div className="candidateActions">
                <button className="ghostButton" disabled={Boolean(active)} onClick={() => setEditing(key)}>Edit suggestion</button>
                <button className="ghostButton" disabled={Boolean(active)} onClick={() => void review(candidate, "reject")}>Reject</button>
                <button className="button primary" disabled={Boolean(active)} onClick={() => void review(candidate, "accept")}>Accept memory</button>
              </div>}
            </article>;
          })}
        </div> : <div className="empty">{status === "pending" ? "Nothing is waiting for review. Suggestions appear here after document analysis finishes." : `No ${status} suggestions found.`}</div>}
      </section>

      {(jobs.length > 0 || chatJobs.length > 0) && <section className="panel">
        <div className="panelHead"><h2>Recent analysis jobs</h2><span className="meta">refreshes every 12 seconds</span></div>
        {[...jobs.map((job) => ({ ...job, origin: "document" })), ...chatJobs.map((job) => ({ ...job, origin: "chatgpt" }))]
          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 10).map((job) => (
            <div className="importSource" key={`${job.origin}:${job.id}`}>
              <div><strong>{job.filename}</strong><div className="meta">{job.candidate_count || 0} suggestions · started {dateText(job.created_at)}</div></div>
              <span className={`badge ${job.status === "failed" ? "failed" : job.status === "ready" ? "ready" : ""}`}>{job.status}</span>
            </div>
          ))}
      </section>}
    </>
  );
}
