"use client";
import { FormEvent, useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import Modal from "@/components/Modal";
import NetworkMap from "@/components/NetworkMap";
import { api } from "@/lib/api";
import { Entity, Graph, entityColour, filterGraph, layoutGraph, matchesEntity } from "@/lib/graph";

type Detail = Entity & {
  relations: { id: string; relation_type: string; from_name: string; to_name: string; confidence: number }[];
  memories: { id: string; title: string; memory_type: string; importance: number }[];
};

export default function KnowledgePage() {
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] });
  const [entities, setEntities] = useState<Entity[]>([]);
  const [limit, setLimit] = useState(80);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [confidence, setConfidence] = useState(0);
  const [focus, setFocus] = useState(false);
  const [labels, setLabels] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    Promise.all([
      api<Graph>(`/api/v1/knowledge/graph?limit=${limit}`, { signal: controller.signal }),
      api<Entity[]>("/api/v1/knowledge/entities?limit=250", { signal: controller.signal }),
    ]).then(([next, list]) => {
      if (controller.signal.aborted) return;
      setGraph(next); setEntities(list); setLoaded(true);
    }).catch(e => { if (!controller.signal.aborted) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [limit, revision]);

  useEffect(() => {
    setDetail(null); setDetailError("");
    if (!selectedId) return;
    const controller = new AbortController();
    api<Detail>(`/api/v1/knowledge/entities/${selectedId}`, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setDetail(value); })
      .catch(e => { if (!controller.signal.aborted) setDetailError(e.message); });
    return () => controller.abort();
  }, [selectedId, revision]);

  const positions = useMemo(() => layoutGraph(graph), [graph]);
  const visible = useMemo(() => filterGraph(graph, query, type, confidence, focus ? selectedId : ""), [graph, query, type, confidence, focus, selectedId]);
  const types = useMemo(() => [...new Set([...graph.nodes, ...entities].map(n => n.entity_type))].sort(), [graph, entities]);
  const list = entities.filter(n => (!type || n.entity_type === type) && matchesEntity(n, query));
  const selected = (detail?.id === selectedId ? detail : null) || entities.find(n => n.id === selectedId) || graph.nodes.find(n => n.id === selectedId);
  const inMap = graph.nodes.some(n => n.id === selectedId);
  const hiddenSelection = selectedId && !visible.nodes.some(n => n.id === selectedId);

  function clearSelection() { setSelectedId(""); setFocus(false); }
  function resetFilters() { setQuery(""); setType(""); setConfidence(0); setFocus(false); }

  async function enrich() {
    setEnriching(true); setError("");
    try {
      const result = await api<{ queued: number }>("/api/v1/knowledge/enrich-all", { method: "POST" });
      setNotice(`Queued ${result.queued} memories for enrichment. Refresh the map after processing finishes.`);
    } catch (e: any) { setError(e.message); }
    finally { setEnriching(false); }
  }

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    setSaving(true); setError("");
    try {
      await api("/api/v1/knowledge/entities", { method: "POST", body: JSON.stringify({
        name: form.get("name"), entity_type: form.get("entity_type") || "other", description: form.get("description"),
        aliases: String(form.get("aliases") || "").split(",").map(x => x.trim()).filter(Boolean),
      }) });
      setShowAdd(false); setRevision(v => v + 1);
    } catch (e: any) { setError(e.message); }
    finally { setSaving(false); }
  }

  return <>
    <Topbar eyebrow="Knowledge core" title="Memory graph" />
    {error && <div className="errorBox" role="alert">{error}{loaded && " The previous map is still shown."} <button className="ghostButton" onClick={() => setRevision(v => v + 1)}>Retry</button></div>}
    {notice && <div className="successBox" role="status">{notice}</div>}
    <div className="knowledgeIntro">
      <p>Follow the people, projects and ideas that connect your memories.</p>
      <div className="row">
        <button className="ghostButton" disabled={loading} onClick={() => setRevision(v => v + 1)}>{loading ? "Loading…" : "Refresh"}</button>
        <button className="ghostButton" onClick={() => setShowAdd(true)}>+ Entity</button>
        <button className="button primary" disabled={enriching} onClick={enrich}>{enriching ? "Queuing…" : "Enrich memories"}</button>
      </div>
    </div>
    <section className="knowledgeFilters" aria-label="Graph filters">
      <label className="knowledgeSearch"><span>Search loaded entities</span><input className="input" type="search" placeholder="Find a name, idea or alias…" value={query} onChange={e => { setQuery(e.target.value); setFocus(false); }} /></label>
      <label><span>Entity type</span><select className="input" value={type} onChange={e => setType(e.target.value)}><option value="">All types</option>{types.map(t => <option key={t} value={t}>{t}</option>)}</select></label>
      <label><span>Relationship confidence</span><select className="input" value={confidence} onChange={e => setConfidence(Number(e.target.value))}><option value={0}>All relationships</option><option value={.7}>70% and above</option><option value={.9}>90% and above</option></select></label>
      <label><span>Map size</span><select className="input" value={limit} disabled={loading} onChange={e => setLimit(Number(e.target.value))}>{[40, 80, 120].map(n => <option key={n} value={n}>Up to {n} entities</option>)}</select></label>
    </section>
    <div className="knowledgeExplorer">
      <section className="panel knowledgeMapPanel" aria-label="Relationship map" aria-busy={loading}>
        <div className="panelHead"><div><h2>Relationship map</h2><span className="meta" aria-live="polite">{visible.nodes.length} entities · {visible.edges.length} relationships{query.trim() && " · matches + neighbours"}{focus && " · focused connections"}</span></div><label className="knowledgeCheck"><input type="checkbox" checked={labels} onChange={e => setLabels(e.target.checked)} />All labels</label></div>
        {loading && !loaded ? <div className="networkEmpty" role="status">Building your map…</div> : visible.nodes.length ?
          <NetworkMap graph={visible} positions={positions} selectedId={selectedId} query={query} allLabels={labels} onSelect={setSelectedId} onClear={clearSelection} /> :
          <div className="networkEmpty"><span className="networkEmptyIcon" aria-hidden="true">◎</span><h3>{error && !loaded ? "Map unavailable" : graph.nodes.length ? "No entities match these filters" : "Your connections start here"}</h3><p>{error && !loaded ? "Retry loading the map above." : graph.nodes.length ? "Try a broader search or show all entity types." : "Enrich your memories to discover entities and their relationships, or add an entity yourself."}</p>{graph.nodes.length > 0 && <button className="ghostButton" onClick={resetFilters}>Clear filters</button>}</div>}
        <div className="knowledgeLegend">{[...new Set(visible.nodes.map(n => n.entity_type))].sort().map(t => <button key={t} className="knowledgeType" onClick={() => setType(type === t ? "" : t)} aria-pressed={type === t}><i style={{ background: entityColour(t) }} />{t}</button>)}<span className="meta">Larger dots = more linked memories</span></div>
        <p className="knowledgeScope">Map shows up to {limit} of the most connected entities. Search covers the {entities.length} loaded directory entries; matching map entities include their direct neighbours. <button onClick={resetFilters}>Clear filters</button></p>
      </section>
      <aside className="panel knowledgeInspector" aria-label={selectedId ? "Entity details" : "Entity directory"}>
        {selectedId ? <>
          <div className="panelHead"><button className="ghostButton" onClick={clearSelection}>← All entities</button><span className="meta">Entity details</span></div>
          <div className="knowledgeDetail" aria-live="polite">
            {selected && <><span className="knowledgeType"><i style={{ background: entityColour(selected.entity_type) }} />{selected.entity_type}</span><h2>{selected.name}</h2></>}
            {detailError ? <div className="errorBox" role="alert">{detailError}<button className="ghostButton" onClick={() => setRevision(v => v + 1)}>Retry</button></div> : !detail || detail.id !== selectedId ? <p className="meta" role="status">Loading entity…</p> : <>
              {detail.description && <p className="knowledgeDescription">{detail.description}</p>}
              {!!detail.aliases?.length && <p className="meta">Also known as {detail.aliases.join(", ")}</p>}
              <div className="knowledgeDetailStats"><span><strong>{detail.memories.length}</strong> linked memories</span><span><strong>{detail.relations.length}</strong> relationships</span></div>
              <button className="ghostButton knowledgeFocus" disabled={!inMap} aria-pressed={focus} onClick={() => { setFocus(v => !v); setQuery(""); setType(""); }}>{focus ? "Show full map" : "Focus connections"}</button>
              {(!inMap || hiddenSelection) && <p className="meta">{!inMap ? "This entity is outside the current map sample. Increase the map size to explore more connections." : "Current filters hide this entity."}</p>}
              <h3>Relationships</h3>{!detail.relations.length && <p className="meta">No relationships yet.</p>}
              {detail.relations.map(r => <div className="knowledgeRelation" key={r.id}><span>{r.from_name}</span><small>{r.relation_type.replaceAll("_", " ")} → <span>{Math.round(r.confidence * 100)}%</span></small><span>{r.to_name}</span></div>)}
              <h3>Linked memories</h3>{!detail.memories.length && <p className="meta">No linked memories yet.</p>}
              {detail.memories.map(m => <a className="entityMemory" href={`/memories/${m.id}`} key={m.id}><strong>{m.title}</strong><span>{m.memory_type} · {m.importance}/10</span></a>)}
            </>}
          </div>
        </> : <>
          <div className="panelHead"><div><h2>Explore entities</h2><span className="meta">{list.length} of {entities.length} loaded</span></div></div>
          <p className="knowledgeDirectoryHint">Select a dot or an entity to see its relationships and memories.</p>
          <div className="knowledgeDirectory">{list.map(n => <button className="knowledgeEntity" key={n.id} onClick={() => setSelectedId(n.id)}><i style={{ background: entityColour(n.entity_type) }} /><span><strong>{n.name}</strong><small>{n.entity_type}</small></span><span className="knowledgeCount" title="Linked memories">{n.memory_count}</span></button>)}{!list.length && <p className="empty">{loading ? "Loading entities…" : "No loaded entities match."}</p>}</div>
        </>}
      </aside>
    </div>
    {showAdd && <Modal title="Create entity" onClose={() => { if (!saving) setShowAdd(false); }}><form className="formGrid" onSubmit={add}><div className="field full"><label htmlFor="entity-name">Name</label><input id="entity-name" className="input" name="name" required /></div><div className="field"><label htmlFor="entity-type">Type</label><input id="entity-type" className="input" name="entity_type" defaultValue="other" /></div><div className="field"><label htmlFor="entity-aliases">Aliases, comma separated</label><input id="entity-aliases" className="input" name="aliases" /></div><div className="field full"><label htmlFor="entity-description">Description</label><textarea id="entity-description" className="textarea" name="description" /></div><div className="field full row" style={{ justifyContent: "flex-end" }}><button className="button primary" disabled={saving}>{saving ? "Creating…" : "Create"}</button></div></form></Modal>}
  </>;
}
