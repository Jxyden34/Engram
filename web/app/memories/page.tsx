"use client";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/Topbar";
import Modal from "@/components/Modal";
import { api, dateText } from "@/lib/api";

export default function MemoriesPage() {
  const [items, setItems] = useState<any[]>([]);
  const [results, setResults] = useState<any[] | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState("");
  const [historical, setHistorical] = useState(false);

  function load() {
    api<any[]>(`/api/v1/memories?limit=100&include_historical=${historical}`).then(setItems).catch((e) => setError(e.message));
  }
  useEffect(load, [historical]);

  async function doSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const query = String(new FormData(e.currentTarget).get("q") || "").trim();
    if (!query) return setResults(null);
    try {
      setResults(await api("/api/v1/search", {
        method: "POST",
        body: JSON.stringify({ query, limit: 20, include_documents: true }),
      }));
    } catch (e: any) { setError(e.message); }
  }

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await api("/api/v1/memories", {
        method: "POST",
        body: JSON.stringify({
          title: f.get("title"),
          content: f.get("content"),
          memory_type: f.get("memory_type") || "general",
          importance: Number(f.get("importance") || 5),
          confidence: Number(f.get("confidence") || 1),
          tags: String(f.get("tags") || "").split(",").map(v => v.trim()).filter(Boolean),
          source_type: "manual",
        }),
      });
      setShowAdd(false);
      load();
    } catch (e: any) { setError(e.message); }
  }

  const visible = results ?? items;

  return (
    <>
      <Topbar eyebrow="Knowledge objects" title="Memories" />
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
        <form className="searchBar" onSubmit={doSearch}>
          <input className="input" name="q" placeholder="Search by meaning, not just words…" />
          <button className="button" type="submit">Search</button>
          {results && <button className="ghostButton" type="button" onClick={() => setResults(null)}>Clear</button>}
        </form>
        <div className="row"><button className="ghostButton" onClick={() => setHistorical(!historical)}>{historical ? "Hide history" : "Show history"}</button><button className="button primary" onClick={() => setShowAdd(true)}>+ New memory</button></div>
      </div>
      {error && <div className="errorBox">{error}</div>}
      <section className="panel">
        <div className="panelHead">
          <h2>{results ? "Semantic results" : "Active memory bank"}</h2>
          <span className="meta">{visible.length} visible</span>
        </div>
        <div className="tableWrap">
          <table>
            <thead><tr><th>Title / source</th><th>Type</th><th>Score</th><th>Importance</th><th>Changed</th></tr></thead>
            <tbody>
              {visible.map((m: any, index) => (
                <tr key={`${m.result_type || "memory"}-${m.id}-${index}`}>
                  <td>
                    {m.result_type === "document_chunk" ? (
                      <>
                        <strong>{m.filename}</strong>
                        <div className="meta" style={{ maxWidth: 660, marginTop: 5 }}>{m.content.slice(0, 180)}…</div>
                      </>
                    ) : (
                      <Link href={`/memories/${m.id}`}>
                        <strong>{m.title}</strong>
                        <div className="meta" style={{ maxWidth: 660, marginTop: 5 }}>{m.content.slice(0, 150)}{m.content.length > 150 ? "…" : ""}</div>
                      </Link>
                    )}
                  </td>
                  <td><span className="badge">{m.result_type === "document_chunk" ? "document" : m.memory_type}</span></td>
                  <td>{m.result_type === "document_chunk" ? "—" : Number(m.memory_score || 0).toFixed(3)}</td>
                  <td>{m.importance ? `${m.importance}/10` : "—"}</td>
                  <td className="meta">{m.updated_at ? dateText(m.updated_at) : `chunk ${m.chunk_index}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!visible.length && <div className="empty">Nothing here yet.</div>}
      </section>

      {showAdd && (
        <Modal title="Create memory" onClose={() => setShowAdd(false)}>
          <form className="formGrid" onSubmit={add}>
            <div className="field full"><label>Title</label><input className="input" name="title" required /></div>
            <div className="field"><label>Type</label><input className="input" name="memory_type" defaultValue="general" /></div>
            <div className="field"><label>Tags, comma separated</label><input className="input" name="tags" /></div>
            <div className="field"><label>Importance 1–10</label><input className="input" type="number" min="1" max="10" name="importance" defaultValue="5" /></div>
            <div className="field"><label>Confidence 0–1</label><input className="input" type="number" min="0" max="1" step=".01" name="confidence" defaultValue="1" /></div>
            <div className="field full"><label>Memory</label><textarea className="textarea" name="content" required /></div>
            <div className="field full row" style={{ justifyContent: "flex-end" }}>
              <button type="button" className="ghostButton" onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="button primary">Commit memory</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
