"use client";

import { FormEvent, useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import { api } from "@/lib/api";

type Project = { id: string; slug: string; name: string };

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");

  async function load() {
    try { setProjects(await api<Project[]>("/api/v1/projects")); }
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

  return <>
    <Topbar eyebrow="Knowledge boundaries" title="Projects" />
    {error && <div className="errorBox">{error}</div>}
    <section className="panel"><div className="panelHead"><h2>Your projects</h2></div>
      {projects.map(project => <div className="healthMemory" key={project.id}>
        <strong>{project.name}</strong><span className="meta">{project.slug}</span>
        <button className="ghostButton" onClick={() => {
          window.localStorage.setItem("memorybank_project_id", project.id);
          document.cookie = `memorybank_project=${project.id}; path=/; SameSite=Lax`;
          window.location.assign("/");
        }}>Open project</button>
      </div>)}
    </section>
    <section className="panel"><div className="panelHead"><h2>Create project</h2></div>
      <form onSubmit={create} className="formGrid">
        <label className="field"><span>Name</span><input className="input" value={name} onChange={e => setName(e.target.value)} required maxLength={120} /></label>
        <label className="field"><span>Slug</span><input className="input" value={slug} onChange={e => setSlug(e.target.value)} required maxLength={63} pattern="[a-z0-9][a-z0-9-]*" /></label>
        <button className="button primary" type="submit">Create project</button>
      </form>
    </section>
  </>;
}
