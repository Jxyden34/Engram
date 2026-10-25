"use client";

import { useCallback, useEffect, useMemo, useState } from 'react';
import Topbar from '@/components/Topbar';
import { api, dateText } from '@/lib/api';
import { DreamArtifact, dreamDocument } from '@/lib/dream-sandbox';

type Dream = {
  id: string; parent_id: string | null; title: string; status: string; needs_review: boolean;
  direction: string; error_message: string | null; created_at: string;
  artifact?: DreamArtifact | null; sources?: {id:string;title:string;content:string}[]; report?: string[];
};
type Schedule = { enabled: boolean; hour_utc: number; next_run_at: string | null };
const active = (d: Dream) => ['queued','running'].includes(d.status) && Date.now()-Date.parse(d.created_at)<15*60*1000;

export default function Dreams() {
  const [dreams, setDreams] = useState<Dream[]>([]);
  const [selected, setSelected] = useState<Dream | null>(null);
  const [direction, setDirection] = useState('');
  const [schedule, setSchedule] = useState<Schedule>({enabled:false,hour_utc:2,next_run_at:null});
  const [preview, setPreview] = useState(false);
  const [nonce, setNonce] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const load = useCallback(async () => {
    try { setDreams(await api<Dream[]>('/api/v1/dreams')); }
    catch(e:any) { setMessage(e.message); }
  }, []);
  useEffect(() => {
    void load();
    api<Schedule>('/api/v1/dreams/schedule').then(setSchedule).catch(e=>setMessage(e.message));
  }, [load]);
  useEffect(() => {
    if (!dreams.some(d=>['queued','running'].includes(d.status))) return;
    const timer=setInterval(()=>void load(),4000);
    return ()=>clearInterval(timer);
  }, [dreams,load]);
  const document = useMemo(()=>selected?.artifact && nonce ? dreamDocument(selected.artifact,nonce) : '',[selected,nonce]);
  async function open(id:string) {
    setPreview(false);setSelected(null);setMessage('');
    try { setSelected(await api<Dream>('/api/v1/dreams/'+id)); }
    catch(e:any) { setMessage(e.message); }
  }
  async function act(action:()=>Promise<void>) {
    setBusy(true);setMessage('');
    try { await action();await load(); }
    catch(e:any) { setMessage(e.message); }
    finally { setBusy(false); }
  }
  function generate(parent?:string) {
    void act(async()=>{
      await api('/api/v1/dreams',{method:'POST',body:JSON.stringify({direction,...(parent?{parent_id:parent}:{})})});
      setMessage('Dream queued. You can leave this page; the worker will build it in the background.');
      setDirection('');
    });
  }
  return <>
    <Topbar eyebrow="Experimental · selected project · Personal and Commercial" title="Dream Lab"/>
    <section className="panel">
      <span className="badge">☾ Turn memories into something you can play with</span>
      <h2>What could your memories invent together?</h2>
      <p>Dream Lab combines up to eight current memories into an offline tool: a calculator, checklist, searchable board, or a new combination. Every dream shows its inspiration and checks.</p>
      <label className="field">Optional direction<textarea className="input" maxLength={1000} rows={3} placeholder="Surprise me—or invent something to help with…" value={direction} onChange={e=>setDirection(e.target.value)}/></label>
      <button className="button" disabled={busy || dreams.some(active)} onClick={()=>generate()}>Dream something up</button>
      <p className="meta">Needs two current memories and a working Ollama chat model. One run at a time per project. Source memories stay unchanged. Prototypes use tested building blocks; arbitrary code and live integrations are outside this preview.</p>
      {message&&<p role="status" className="errorBox">{message}</p>}
    </section>
    <section className="panel">
      <h2>Wake up to a new dream</h2>
      <label><input type="checkbox" checked={schedule.enabled} onChange={e=>setSchedule({...schedule,enabled:e.target.checked})}/> Enable one nightly dream for this project</label>
      <label className="field">Hour (UTC)<input className="input" type="number" min={0} max={23} value={schedule.hour_utc} onChange={e=>setSchedule({...schedule,hour_utc:Number(e.target.value)})}/></label>
      <button className="ghostButton" disabled={busy} onClick={()=>void act(async()=>{
        setSchedule(await api<Schedule>('/api/v1/dreams/schedule',{method:'PUT',body:JSON.stringify({enabled:schedule.enabled,hour_utc:schedule.hour_utc})}));
        setMessage('Nightly schedule saved.');
      })}>Save schedule</button>
      <p className="meta">{schedule.next_run_at?`Next run: ${dateText(schedule.next_run_at)}`:'Nightly generation is off.'} The server and worker must be running. Busy or full projects skip that night.</p>
    </section>
    <section className="panel"><h2>Your dreams</h2>
      {!dreams.length&&<p>No dreams yet. Add two memories, then start your first experiment.</p>}
      {dreams.map(d=><article key={d.id} className="healthMemory">
        <button className="ghostButton" onClick={()=>void open(d.id)}>{d.title}</button>{' '}<span className="badge">{d.needs_review?'Sources changed':d.status}</span>
        <p className="meta">{dateText(d.created_at)}{d.parent_id?' · Evolved from an earlier dream':''}</p>
        {d.error_message&&<p>{d.error_message}</p>}
        <button className="ghostButton" disabled={busy} onClick={()=>void act(async()=>{
          await api('/api/v1/dreams/'+d.id,{method:'DELETE'});
          if(selected?.id===d.id){setSelected(null);setPreview(false);}
        })}>Destroy dream</button>
      </article>)}
    </section>
    {selected&&<section className="panel"><h2>{selected.title}</h2>
      {selected.needs_review&&<p role="alert">A source changed or became unavailable. The old prototype and quotations are withheld. Generate a fresh dream from current memories.</p>}
      {selected.error_message&&<p>{selected.error_message}</p>}
      {selected.artifact&&<>
        <p>{selected.artifact.premise}</p>
        <div className="actions">
          <button className="button" onClick={()=>{setNonce(crypto.randomUUID().replaceAll('-',''));setPreview(true);}}>Open disposable sandbox</button>{' '}
          <button className="ghostButton" disabled={busy||selected.status==='kept'} onClick={()=>void act(async()=>{
            await api('/api/v1/dreams/'+selected.id+'/keep',{method:'POST'});setSelected({...selected,status:'kept'});
          })}>{selected.status==='kept'?'Kept':'Keep dream'}</button>{' '}
          <button className="ghostButton" disabled={busy||dreams.some(active)} onClick={()=>generate(selected.id)}>Evolve using direction above</button>
        </div>
        {preview&&<div style={{marginTop:20}}>
          <button className="ghostButton" onClick={()=>setPreview(false)}>Close and reset sandbox</button>
          <iframe title="Dream prototype sandbox" sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={document} style={{width:'100%',height:640,border:'1px solid #737f9d',borderRadius:16,marginTop:12}}/>
        </div>}
        <h3>Experiment report</h3><ul>{selected.report?.map((r,i)=><li key={i}>{r}</li>)}</ul>
        <h3>Try it yourself</h3><ol>{selected.artifact.how_to_test.map((r,i)=><li key={i}>{r}</li>)}</ol>
        <p><strong>Limitations:</strong> {selected.artifact.limitations}</p>
        <h3>What inspired this?</h3>
        {selected.artifact.inspiration.map((c,i)=>{
          const source=selected.sources?.[c.source-1];
          return source?<blockquote key={i}><a href={'/memories/'+source.id}>{source.title}</a><p>“{c.quote}”</p></blockquote>:null;
        })}
        <p className="meta">Keeping a dream saves the prototype here. It does not deploy it, connect services or create factual memories. Closing the sandbox discards its input values.</p>
      </>}
      {['queued','running'].includes(selected.status)&&<button className="ghostButton" onClick={()=>void open(selected.id)}>Refresh this dream</button>}
    </section>}
  </>;
}
