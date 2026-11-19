"use client";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/Topbar";
import Modal from "@/components/Modal";
import ActionGroup from "@/components/ActionGroup";
import { api, dateText } from "@/lib/api";

export default function MemoriesPage() {
  const [items, setItems] = useState<any[]>([]);
  const [results, setResults] = useState<any[] | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState("");
  const [historical, setHistorical] = useState(false);
  const [archived, setArchived] = useState(false);
  const [searching, setSearching] = useState(false);
  const [entities, setEntities] = useState<{id:string;name:string}[] | null>(null);

  function load() {
    api<any[]>(`/api/v1/memories?limit=100&include_historical=${historical}&include_archived=${archived}`).then(setItems).catch((e) => setError(e.message));
  }
  useEffect(() => { setResults(null); load(); }, [historical, archived]);

  async function doSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const query = String(form.get("q") || "").trim();
    if (!query) return setResults(null);
    setError("");
    setSearching(true);
    try {
      setResults(await api("/api/v1/search", {
        method: "POST",
        body: JSON.stringify({
          query, limit: 20, include_documents: true, include_knowledge: true,
          include_historical: historical, include_archived: archived,
          result_type: form.get("result_type") || null,
          source_type: String(form.get("source_type") || "").trim() || null,
          since: form.get("since") || null, until: form.get("until") || null,
          entity_id: form.get("entity_id") || null,
          min_importance: form.get("min_importance") || null,
          min_confidence: form.get("min_confidence") || null,
        }),
      }));
    } catch (e: any) { setError(e.message); }
    finally { setSearching(false); }
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
      <div className="pageToolbar">
        <form id="project-search" className="searchBar" onSubmit={doSearch}>
          <input className="input" name="q" aria-label="Search this project" placeholder="Search memories, documents, entities and events…" />
          <button className="button" type="submit" disabled={searching}>{searching ? "Searching…" : "Search"}</button>
          {results && <button className="ghostButton" type="button" onClick={() => setResults(null)}>Clear</button>}
        </form>
        <div className="toolbarActions"><ActionGroup label="Memory visibility"><button className="ghostButton" aria-pressed={archived} onClick={() => setArchived(!archived)}>Archived</button><button className="ghostButton" aria-pressed={historical} onClick={() => setHistorical(!historical)}>History</button></ActionGroup><button className="button primary" onClick={() => setShowAdd(true)}>+ New memory</button></div>
      </div>
      <details className="panel" onToggle={event => {
        if (event.currentTarget.open && entities === null) {
          api<{id:string;name:string}[]>("/api/v1/knowledge/entities?limit=250")
            .then(setEntities).catch((e) => setError(e.message));
        }
      }}>
        <summary>Search filters</summary>
        <div className="formGrid" style={{marginTop: 12}}>
          <label className="field">Content type
            <select className="select" name="result_type" form="project-search">
              <option value="">All types</option><option value="memory">Memories</option>
              <option value="document_chunk">Document excerpts</option>
              <option value="entity">Entities</option><option value="event">Events</option>
            </select>
          </label>
          <label className="field">Source type
            <input className="input" name="source_type" form="project-search" maxLength={80} placeholder="e.g. browser_capture" />
          </label>
          <label className="field">From <input className="input" type="date" name="since" form="project-search" /></label>
          <label className="field">Through <input className="input" type="date" name="until" form="project-search" /></label>
          <label className="field">Linked entity (memories)
            <select className="select" name="entity_id" form="project-search">
              <option value="">Any entity</option>
              {entities?.map(entity => <option key={entity.id} value={entity.id}>{entity.name}</option>)}
            </select>
          </label>
          <label className="field">Minimum importance (memories)
            <input className="input" type="number" min={1} max={10} name="min_importance" form="project-search" />
          </label>
          <label className="field">Minimum confidence (memories)
            <input className="input" type="number" min={0} max={1} step={0.01} name="min_confidence" form="project-search" />
          </label>
        </div>
      </details>
      {error && <div className="errorBox">{error}</div>}
      <section className="panel">
        <div className="panelHead">
          <h2>{results ? "Search results" : "Active memories"}</h2>
          <span className="meta">{visible.length} visible</span>
        </div>
        <div className="tableWrap">
          <table>
            <thead><tr><th>Title / source</th><th>Type</th><th>Score</th><th>Importance</th><th>Changed</th><th>Archive</th></tr></thead>
            <tbody>
              {visible.map((m: any, index) => (
                <tr key={`${m.result_type || "memory"}-${m.id}-${index}`}>
                  <td>
                    {m.result_type === "document_chunk" ? (
                      <>
                        <strong>{m.filename}</strong>
                        <div className="meta" style={{ maxWidth: 660, marginTop: 5 }}>{m.content.slice(0, 180)}…</div>
                      </>
                    ) : m.result_type === "entity" || m.result_type === "event" ? (
                      <Link href={m.result_type === "entity" ? "/knowledge" : "/timeline"}>
                        <strong>{m.title}</strong>
                        {m.content && <div className="meta">{m.content.slice(0, 180)}</div>}
                      </Link>
                    ) : (
                      <Link href={`/memories/${m.id}`}>
                        <strong>{m.title}</strong> {m.pinned&&<span className="badge">Pinned</span>}
                        <div className="meta" style={{ maxWidth: 660, marginTop: 5 }}>{m.content.slice(0, 150)}{m.content.length > 150 ? "…" : ""}</div>
                      </Link>
                    )}
                    {m.match_reasons?.length > 0 && <div className="meta">Matched: {m.match_reasons.join(", ")}</div>}
                  </td>
                  <td><span className="badge">{m.result_type === "document_chunk" ? "document" : m.memory_type || m.result_type}</span></td>
                  <td>{m.retrieval_score != null ? Number(m.retrieval_score).toFixed(3) : Number(m.memory_score || 0).toFixed(3)}</td>
                  <td>{m.importance ? `${m.importance}/10` : "—"}</td>
                  <td className="meta">{m.updated_at ? dateText(m.updated_at) : `chunk ${m.chunk_index}`}</td>
                  <td>{m.archived_at ? <span className="badge">Archived</span> : "—"}</td>
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
