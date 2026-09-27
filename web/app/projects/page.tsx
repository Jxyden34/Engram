"use client";

import { FormEvent, useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import { api } from "@/lib/api";

type Project = { id: string; slug: string; name: string };
type SearchResult = { id: string; title: string; content: string; project_id: string; project_name: string; search_score: number };

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [items, me] = await Promise.all([
        api<Project[]>("/api/v1/projects"), api<{ is_admin: boolean }>("/api/v1/auth/me"),
      ]);
      setProjects(items); setIsAdmin(me.is_admin);
    }
    catch (e: any) { setError(e.message); }
  }
  useEffect(() => { void load(); }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api("/api/v1/projects", { method: "POST", body: JSON.stringify({ name, slug }) });
      setName(""); setSlug(""); await load();
    } catch (e: any) { setError(e.message); }
  }

  async function search(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      setResults(await api<SearchResult[]>("/api/v1/projects/search", {
        method: "POST", body: JSON.stringify({ query, project_ids: selected, limit: 30 }),
      }));
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  function openProject(projectId: string, path = "/") {
    window.localStorage.setItem("engram_project_id", projectId);
    document.cookie = `engram_project=${projectId}; path=/; SameSite=Lax`;
    window.location.assign(path);
  }

  return <>
    <Topbar eyebrow="Knowledge boundaries" title="Projects" />
    {error && <div className="errorBox">{error}</div>}
    <section className="panel"><div className="panelHead"><h2>Your projects</h2></div>
      {projects.map(project => <div className="healthMemory" key={project.id}>
        <strong>{project.name}</strong><span className="meta">{project.slug}</span>
        {isAdmin && <label className="meta"><input type="checkbox" checked={selected.includes(project.id)} disabled={!selected.includes(project.id) && selected.length >= 20} onChange={e => { setSelected(e.target.checked ? [...selected, project.id] : selected.filter(id => id !== project.id)); setResults(null); }} /> Include in search</label>}
        <button className="ghostButton" onClick={() => openProject(project.id)}>Open project</button>
      </div>)}
    </section>
    {isAdmin && <section className="panel"><div className="panelHead"><h2>Search selected projects</h2></div>
      <p className="meta">Choose projects above. Results show their source project and open there.</p>
      <form className="searchBar" onSubmit={search}>
        <input className="input" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search memories…" required maxLength={5000} />
        <button className="button" disabled={busy || selected.length === 0} type="submit">{busy ? "Searching…" : `Search ${selected.length} project${selected.length === 1 ? "" : "s"}`}</button>
      </form>
      {results && <div style={{ marginTop: 18 }}>
        {!results.length && <div className="empty">No matching memories.</div>}
        {results.map(item => <div className="healthMemory" key={`${item.project_id}-${item.id}`}>
          <span className="badge">{item.project_name}</span>
          <strong>{item.title}</strong>
          <span className="meta">{item.content.slice(0, 180)}{item.content.length > 180 ? "…" : ""}</span>
          <button className="ghostButton" onClick={() => openProject(item.project_id, `/memories/${item.id}`)}>Open memory</button>
        </div>)}
      </div>}
    </section>}
    {isAdmin && <section className="panel"><div className="panelHead"><h2>Create project</h2></div>
      <form onSubmit={create} className="formGrid">
        <label className="field"><span>Name</span><input className="input" value={name} onChange={e => setName(e.target.value)} required maxLength={120} /></label>
        <label className="field"><span>Slug</span><input className="input" value={slug} onChange={e => setSlug(e.target.value)} required maxLength={63} pattern="[a-z0-9][a-z0-9-]*" /></label>
        <button className="button primary" type="submit">Create project</button>
      </form>
    </section>}
  </>;
}
