"use client";

import {useEffect,useState} from 'react';
import Topbar from '@/components/Topbar';
import {api,dateText} from '@/lib/api';

type Timing={count:number;errors:number;error_rate:number|null;mean_ms:number|null;p95_upper_ms:number|null;p95_overflow:boolean};
type Snapshot={project_id:string;generated_at:string;latency:{status:string;window_started_at?:string;operations:Record<string,Timing>};
  services:Record<string,{status:string;latency_ms?:number|null}>;
  queue:{status:string;scope:string;queued?:number;started_registry?:number;failed_registry?:number};
  project:{status:string;documents?:{queued:number;processing:number;failed:number;ready_24h:number;ready_per_hour_24h:number};
    candidates?:{pending:number;accepted_24h:number;rejected_24h:number;acceptance_rate_24h:number|null};
    connectors?:{total:number;enabled:number;failing:number;overdue:number;last_sync_at:string|null};
    connector_runs_24h?:{ready:number;failed:number;items_changed:number}}};
const percent=(value:number|null|undefined)=>value==null?'No reviewed samples':`${(value*100).toFixed(1)}%`;
const ms=(value:number|null|undefined)=>value==null?'—':`${value.toLocaleString()} ms`;
export default function ObservabilityPage(){
  const [data,setData]=useState<Snapshot|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  async function load(){setBusy(true);setError('');try{setData(await api<Snapshot>('/api/v1/observability'));}catch(e:any){setError(e.message);}finally{setBusy(false);}}
  useEffect(()=>{void load();},[]);
  return <><Topbar eyebrow="Service performance" title="Observability"/>
    <p className="meta">Administrator access required. Content and timing totals apply to the selected project. Service probes and the shared job queue describe this deployment.</p>
    <button className="button" disabled={busy} onClick={load}>{busy?'Refreshing…':'Refresh metrics'}</button>
    {error&&<p className="errorBox" role="alert">{error}</p>}
    {data&&<><p className="meta" role="status">Snapshot {dateText(data.generated_at)}</p>
      <section className="panel"><h2>Service readiness</h2><div className="grid4">{Object.entries(data.services).map(([name,service])=><div className="miniStat" key={name}><span>{name.replaceAll('_',' ')}</span><strong>{service.status==='ok'?'Ready':'Unavailable'}</strong>{service.latency_ms!=null&&<span>{ms(service.latency_ms)}</span>}</div>)}</div><p className="meta">Readiness checks do not prove backup health, bucket permissions or model answer quality. PostgreSQL includes a project query check.</p></section>
      <section className="panel"><h2>Latency · approximately 24 hours</h2>
        {data.latency.status!=='ok'?<p role="status">Timing storage is unavailable.</p>:<><p className="meta">Five-minute aggregates since {data.latency.window_started_at?dateText(data.latency.window_started_at):'—'}. Empty samples stay empty. P95 is a histogram upper bound.</p>
          <div style={{overflowX:'auto'}}><table className="table"><thead><tr><th>Operation</th><th>Samples</th><th>Mean</th><th>P95 ≤</th><th>Errors</th></tr></thead><tbody>{Object.entries(data.latency.operations).map(([name,timing])=><tr key={name}><td>{name==='api'?'API response headers':name==='embedding'?'Embeddings':'Local model JSON requests'}</td><td>{timing.count}</td><td>{ms(timing.mean_ms)}</td><td>{timing.p95_overflow?'>300,000 ms':ms(timing.p95_upper_ms)}</td><td>{timing.count?`${timing.errors} (${percent(timing.error_rate)})`:'—'}</td></tr>)}</tbody></table></div>
          <p className="meta">API timings exclude login, unresolved authentication and this metrics endpoint; errors include HTTP 4xx/5xx. Model timings include network/JSON parsing, not later citation checks. Counters start when this build runs and expire automatically.</p></>}
      </section>
      <section className="panel"><h2>Shared job queue</h2><p className="meta">Deployment-wide document-ingest queue; registry sizes can include entries awaiting worker cleanup.</p>{data.queue.status==='ok'?<div className="grid4">{[['Queued',data.queue.queued],['Started registry',data.queue.started_registry],['Failed registry',data.queue.failed_registry]].map(([label,value])=><div className="miniStat" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>:<p role="status">Queue metrics unavailable.</p>}</section>
      {data.project.status!=='ok'?<p className="errorBox" role="status">Project metrics unavailable.</p>:<>
        <section className="panel"><h2>Project ingestion</h2><div className="grid4">{[['Ready in 24h',data.project.documents?.ready_24h],['Average ready/hour',data.project.documents?.ready_per_hour_24h],['Queued / processing',`${data.project.documents?.queued} / ${data.project.documents?.processing}`],['Failed documents',data.project.documents?.failed]].map(([label,value])=><div className="miniStat" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div></section>
        <section className="panel"><h2>Candidate review · last 24 hours</h2><div className="grid4">{[['Pending',data.project.candidates?.pending],['Accepted',data.project.candidates?.accepted_24h],['Rejected',data.project.candidates?.rejected_24h],['Acceptance rate',percent(data.project.candidates?.acceptance_rate_24h)]].map(([label,value])=><div className="miniStat" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><p className="meta">Accepted ÷ (accepted + rejected) across conversation and document candidates reviewed in this period.</p></section>
        <section className="panel"><h2>Project connectors</h2><div className="grid4">{[['Enabled / total',`${data.project.connectors?.enabled} / ${data.project.connectors?.total}`],['Failing enabled',data.project.connectors?.failing],['Overdue by 5+ minutes',data.project.connectors?.overdue],['Failed runs in 24h',data.project.connector_runs_24h?.failed]].map(([label,value])=><div className="miniStat" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><p className="meta">Latest recorded sync: {data.project.connectors?.last_sync_at?dateText(data.project.connectors.last_sync_at):'none'}. Completed runs in 24h: {data.project.connector_runs_24h?.ready}; items changed: {data.project.connector_runs_24h?.items_changed}.</p></section>
      </>}
    </>}
  </>;
}
