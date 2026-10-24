"use client";

import {useEffect,useState} from 'react';
import Link from 'next/link';
import {api,dateText} from '@/lib/api';

type Action={id:string;memory_id:string;title:string;kind:string;actor:string;reason:string;created_at:string;can_undo:boolean;undone_at?:string;undone_by?:string;undo_reason?:string};
export default function LifecycleHistory({memoryId,revision,onChange}:{memoryId?:string;revision?:string;onChange?:()=>void}){
  const [items,setItems]=useState<Action[]>([]),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  async function load(){setItems(await api<Action[]>('/api/v1/lifecycle/actions'+(memoryId?`?memory_id=${memoryId}`:'')));}
  useEffect(()=>{load().catch(e=>setError(e.message));},[memoryId,revision]);
  async function undo(id:string){setBusy(true);setError('');setNotice('');try{
    await api(`/api/v1/lifecycle/actions/${id}/undo`,{method:'POST',body:JSON.stringify({reason})});
    await load();onChange?.();setNotice('Action reversed. Its original record and reversal remain in the audit history.');
  }catch(e:any){setError(e.message);}finally{setBusy(false);}}
  return <section className="panel"><h2>Recent lifecycle actions</h2><p className="meta">Up to 50 actions from the last seven days. Undo restores the previous archive state, or archives a generated consolidation summary. Original source memories stay unchanged. Newer edits prevent quick undo.</p>
    {error&&<p className="errorBox" role="alert">{error}</p>}{notice&&<p className="successBox" role="status">{notice}</p>}
    <label htmlFor={memoryId?'memory-undo-reason':'project-undo-reason'}>Reason for undo</label><input id={memoryId?'memory-undo-reason':'project-undo-reason'} className="input" value={reason} minLength={3} maxLength={1000} onChange={e=>setReason(e.target.value)} placeholder="Why reverse this action?"/>
    <button className="ghostButton" disabled={busy} onClick={()=>load().catch(e=>setError(e.message))}>Refresh actions</button>
    {!items.length&&<p className="meta">No recent actions recorded.</p>}{items.map(item=><div key={item.id} style={{padding:'12px 0',borderTop:'1px solid #22262c'}}><Link href={`/memories/${item.memory_id}`}>{item.title}</Link><p className="meta">{item.kind} · {dateText(item.created_at)} · {item.actor}</p><p>{item.reason}</p>{item.undone_at?<p className="meta">Undone {dateText(item.undone_at)} by {item.undone_by}: {item.undo_reason}</p>:item.can_undo?<button className="button" disabled={busy||reason.trim().length<3} onClick={()=>undo(item.id)}>Undo {item.kind}</button>:<p className="meta">Memory changed since this action. Review it manually.</p>}</div>)}
  </section>;
}
