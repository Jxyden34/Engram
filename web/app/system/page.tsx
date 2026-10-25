"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/Topbar";
import ActionGroup from "@/components/ActionGroup";
import { api, dateText } from "@/lib/api";
import { version as clientVersion } from "@/package.json";

type MemoryHealth = {
  score:number;
  counts:{current_memories:number;historical_memories:number;entities:number;events:number;unenriched:number};
  issues:{type:string;label:string;count:number;severity:string}[];
  duplicate_pairs:{memory_id:string;duplicate_id:string;title:string;duplicate_title:string;similarity:number}[];
  stale_memories:{id:string;title:string;memory_type:string;updated_at:string}[];
};
type Readiness = {generated_at:string;services:Record<string,{status:string;latency_ms?:number|null}>};
const serviceNames:Record<string,string>={postgresql:"Database",redis:"Queue & cache",object_storage:"Document storage",ollama:"Local AI"};

export default function HealthPage() {
  const [server,setServer]=useState<{version:string;status:string}|null>(null);
  const [data,setData]=useState<MemoryHealth|null>(null);
  const [readiness,setReadiness]=useState<Readiness|null>(null);
  const [admin,setAdmin]=useState(false),[canEnrich,setCanEnrich]=useState(false);
  const [busy,setBusy]=useState(true),[enriching,setEnriching]=useState(false);
  const [checked,setChecked]=useState<string|null>(null);
  const [errors,setErrors]=useState<string[]>([]),[serviceError,setServiceError]=useState(""),[notice,setNotice]=useState("");

  async function load() {
    setBusy(true);setErrors([]);setServiceError("");
    const [health,memories,user]=await Promise.allSettled([
      api<{version:string;status:string}>("/health"),api<MemoryHealth>("/api/v1/health/summary"),
      api<{is_admin:boolean;scopes:string[]}>("/api/v1/auth/me"),
    ]);
    const failures:string[]=[];
    setServer(health.status==="fulfilled"?health.value:null);
    setData(memories.status==="fulfilled"?memories.value:null);
    if(health.status==="rejected")failures.push("Server information: "+health.reason.message);
    if(memories.status==="rejected")failures.push("Memory quality: "+memories.reason.message);
    const isAdmin=user.status==="fulfilled"&&user.value.is_admin;
    setAdmin(isAdmin);setCanEnrich(user.status==="fulfilled"&&user.value.scopes.includes("memory:write"));
    if(user.status==="rejected")failures.push("Account permissions: "+user.reason.message);
    setReadiness(null);
    if(isAdmin){try{setReadiness(await api<Readiness>("/api/v1/observability"));}catch(e:any){setServiceError(e.message);}}
    setErrors(failures);setChecked(new Date().toISOString());setBusy(false);
  }
  useEffect(()=>{void load();},[]);
  async function enrich() {
    setEnriching(true);setNotice("");
    try{const result=await api<{queued:number}>("/api/v1/knowledge/enrich-all",{method:"POST"});setNotice(`Queued ${result.queued} memories for enrichment. Results appear as background processing completes.`);}
    catch(e:any){setErrors(previous=>[...previous,e.message]);}finally{setEnriching(false);}
  }
  return <>
    <Topbar eyebrow="Your Engram installation" title="Health & about"/>
    <div className="pageToolbar"><p className="pageIntro">Your server, its services and the quality of your project’s memories, in one place.</p><ActionGroup label="Health page actions"><button className="button" onClick={load} disabled={busy}>{busy?"Checking…":"Refresh checks"}</button><Link className="ghostButton" href="/settings">Settings</Link></ActionGroup></div>
    {errors.map((error,index)=><p className="errorBox" role="alert" key={index}>{error}</p>)}
    {notice&&<p className="successBox" role="status">{notice}</p>}
    <section className="panel installationHero" aria-label="Installation information" aria-busy={busy}>
      <div className="installationIdentity"><div className="brandMark" aria-hidden="true"/><div><span className="eyebrow">Private memory platform</span><h2>Engram</h2><p>Your knowledge. Your context. Your server.</p></div></div>
      <span className={`badge ${server?.status==="ok"?"ready":busy?"pending":"failed"}`} role="status">{server?.status==="ok"?"API reachable":busy?"Checking server":"Server unavailable"}</span>
      <dl className="installationFacts"><div><dt>Server version</dt><dd>{server?`v${server.version}`:busy?"Checking…":"Unavailable"}</dd></div><div><dt>Web interface</dt><dd>v{clientVersion}</dd></div><div><dt>Last check</dt><dd>{checked?dateText(checked):"In progress"}</dd></div></dl>
      <div className="installationLinks"><a href={server?`https://github.com/Jxyden34/Engram/releases/tag/v${encodeURIComponent(server.version)}`:"https://github.com/Jxyden34/Engram/releases"} target="_blank" rel="noopener noreferrer">Release notes ↗</a><a href="https://github.com/Jxyden34/Engram/blob/main/docs/OPERATIONS.md" target="_blank" rel="noopener noreferrer">Server guide ↗</a><Link href="/about">About Engram</Link></div>
    </section>
    <section className="panel" aria-label="Service readiness">
      <div className="panelHead"><div><h2>Service readiness</h2><p className="sectionDescription">Point-in-time checks of the services behind your installation.</p></div>{admin&&<Link className="ghostButton" href="/observability">Detailed metrics</Link>}</div>
      {readiness?<><div className="serviceGrid">{Object.entries(readiness.services).map(([name,service])=><div className="serviceCard" key={name}><span>{serviceNames[name]||name}</span><strong><i className={`statusDot ${service.status==="ok"?"ready":"failed"}`} aria-hidden="true"/>{service.status==="ok"?"Ready":"Unavailable"}</strong><small>{service.latency_ms!=null?`${service.latency_ms.toLocaleString()} ms response`:"Readiness check"}</small></div>)}</div><p className="meta">Checked {dateText(readiness.generated_at)}. Readiness is separate from backup integrity and AI answer quality.</p></>:<p className={serviceError?"errorBox":"empty"} role="status">{serviceError?`Service checks unavailable: ${serviceError}`:busy?"Checking service access…":admin?"Service checks unavailable.":"Detailed service checks require an administrator browser session. Your server version and memory quality are shown separately."}</p>}
      <div className="statusDestinations"><Link href="/disaster-recovery"><strong>Backup & recovery</strong><span>Backup integrity, restore tests and replication →</span></Link><Link href="/observability"><strong>Performance</strong><span>Latency, ingestion and the shared job queue →</span></Link></div>
    </section>
    {data?<>
      <section className="panel memoryQuality">
        <div className="panelHead"><div><h2>Memory quality</h2><p className="sectionDescription">Checks apply to the selected project. This score describes knowledge quality, not server availability.</p></div><Link className="ghostButton" href="/memories">Browse memories</Link></div>
        <div className="qualityOverview"><div className={`healthScore score-${data.score>=85?"good":data.score>=65?"warn":"bad"}`}>{data.score}<span>/100</span></div><div><strong>{data.score>=85?"Looking good":data.score>=65?"A little attention needed":"Review recommended"}</strong><p className="sectionDescription">Contradictions, duplicate evidence, confidence, age and graph coverage.</p></div></div>
        <div className="grid4">{[["Current memories",data.counts.current_memories],["Historical memories",data.counts.historical_memories],["Entities",data.counts.entities],["Events",data.counts.events]].map(([label,value])=><div className="miniStat" key={label}><span>{label}</span><strong>{Number(value).toLocaleString()}</strong></div>)}</div>
        <div className="healthIssues">{data.issues.map(issue=><div className={`healthIssue ${issue.severity}`} key={issue.type}><span className="healthDot" aria-hidden="true"/><div><strong>{issue.label}</strong><div className="meta">{issue.count?`${issue.count.toLocaleString()} to review`:"No findings"}</div></div><b>{issue.count}</b></div>)}</div>
        <div className="pageToolbar qualityActions"><p className="meta">Enrichment adds missing graph context through your configured AI service.</p><ActionGroup label="Memory quality actions"><Link className="ghostButton" href="/imports">Review inbox</Link>{canEnrich&&<button className="button" disabled={enriching||!data.counts.unenriched} onClick={enrich}>{enriching?"Queuing…":"Enrich missing knowledge"}</button>}</ActionGroup></div>
      </section>
      <div className="split"><section className="panel"><div className="panelHead"><h2>Likely duplicates</h2><span className="badge">≥94% similar</span></div>{data.duplicate_pairs.map(pair=><div className="healthPair" key={`${pair.memory_id}-${pair.duplicate_id}`}><Link href={`/memories/${pair.memory_id}`}>{pair.title}</Link><span>{Math.round(pair.similarity*100)}%</span><Link href={`/memories/${pair.duplicate_id}`}>{pair.duplicate_title}</Link></div>)}{!data.duplicate_pairs.length&&<div className="empty">No strong duplicate pairs.</div>}</section><section className="panel"><div className="panelHead"><h2>Potentially stale</h2><span className="meta">Old and unused</span></div>{data.stale_memories.map(memory=><Link className="healthMemory" href={`/memories/${memory.id}`} key={memory.id}><strong>{memory.title}</strong><span>{memory.memory_type} · updated {dateText(memory.updated_at)}</span></Link>)}{!data.stale_memories.length&&<div className="empty">Nothing looks stale.</div>}</section></div>
    </>:busy?<section className="panel" role="status">Loading project memory quality…</section>:null}
  </>;
}
