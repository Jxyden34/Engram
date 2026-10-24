"use client";
import { FormEvent,useEffect,useState } from 'react';
import Link from 'next/link';
import { api,dateText } from '@/lib/api';

type Item={id:string;title:string;content:string};
type Draft={id:string;title:string;content:string;created_at:string;source_versions:Record<string,string>;result_memory_id?:string|null;evidence_changed?:boolean;
  sources:{id:string;title:string}[];claims:{text:string;citations:{source:number;quote:string}[]}[]};
export default function ClusterConsolidation(){
  const [items,setItems]=useState<Item[]>([]),[selected,setSelected]=useState<string[]>([]),[filter,setFilter]=useState('');
  const [drafts,setDrafts]=useState<{id:string;created_at:string;result_memory_id?:string|null}[]>([]);
  const [draft,setDraft]=useState<Draft|null>(null),[title,setTitle]=useState(''),[content,setContent]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  async function load(){const [memories,history]=await Promise.all([api<Item[]>('/api/v1/memories?limit=100'),api<typeof drafts>('/api/v1/intelligence/clusters')]);setItems(memories);setDrafts(history);}
  useEffect(()=>{load().catch(e=>setError(e.message));},[]);
  function show(next:Draft){setDraft(next);setTitle('Reviewed cluster summary');setContent(next.content);}
  async function generate(e:FormEvent){e.preventDefault();setBusy(true);setError('');setNotice('');try{
    show(await api<Draft>('/api/v1/intelligence/clusters',{method:'POST',body:JSON.stringify({memory_ids:selected})}));await load();
  }catch(e:any){setError(e.message);}finally{setBusy(false);}}
  async function open(id:string){setBusy(true);setError('');try{show(await api<Draft>(`/api/v1/intelligence/clusters/${id}`));}catch(e:any){setError(e.message);}finally{setBusy(false);}}
  async function approve(e:FormEvent){e.preventDefault();if(!draft)return;setBusy(true);setError('');try{
    const result=await api<{result_memory_id:string}>(`/api/v1/intelligence/clusters/${draft.id}/approve`,{method:'POST',body:JSON.stringify({title,content,source_versions:draft.source_versions})});
    setDraft({...draft,result_memory_id:result.result_memory_id});setNotice('Reviewed summary saved with links to every original. Original memories are unchanged.');await load();
  }catch(e:any){setError(e.message);}finally{setBusy(false);}}
  return <section className="panel"><h2>Consolidate a memory group</h2><p className="meta">Select 3–10 related current memories. Review the proposed summary and source quotes before saving. Showing up to 100 current memories.</p>
    {error&&<p className="errorBox" role="alert">{error}</p>}{notice&&<p className="successBox" role="status">{notice}</p>}
    <form onSubmit={generate}><label htmlFor="cluster-filter">Find memories</label><input id="cluster-filter" className="input" value={filter} onChange={e=>setFilter(e.target.value)}/>
      <div style={{maxHeight:280,overflow:'auto'}}>{items.filter(item=>item.title.toLowerCase().includes(filter.toLowerCase())).map(item=><div key={item.id}>
        <label><input type="checkbox" checked={selected.includes(item.id)} disabled={busy||(!selected.includes(item.id)&&selected.length>=10)} onChange={e=>setSelected(e.target.checked?[...selected,item.id]:selected.filter(id=>id!==item.id))}/>{item.title}</label>
        <Link href={`/memories/${item.id}`}> Read source</Link>
      </div>)}</div><button className="button" disabled={busy||selected.length<3}>{busy?'Working…':`Draft group summary (${selected.length}/10)`}</button></form>
    {draft&&<div><h3>Review the proposed summary</h3>{draft.claims.map((claim,i)=><div key={i}><p>{claim.text}</p>{claim.citations.map((citation,j)=><blockquote key={j}><p>{citation.quote}</p><Link href={`/memories/${draft.sources[citation.source-1].id}`}>{draft.sources[citation.source-1].title}</Link></blockquote>)}</div>)}
      {draft.result_memory_id?<Link href={`/memories/${draft.result_memory_id}`}>Open reviewed summary</Link>:draft.evidence_changed?<p className="errorBox">Sources changed. Generate a fresh draft before approving.</p>:<form onSubmit={approve}>
        <label htmlFor="cluster-title">Reviewed title</label><input id="cluster-title" className="input" value={title} onChange={e=>setTitle(e.target.value)} required maxLength={300}/>
        <label htmlFor="cluster-content">Reviewed summary</label><textarea id="cluster-content" className="textarea" value={content} onChange={e=>setContent(e.target.value)} required maxLength={10000}/>
        <label><input type="checkbox" required/> I reviewed every source, quote and summary statement.</label><button className="button primary" disabled={busy}>Save reviewed consolidation</button>
      </form>}
    </div>}
    <details><summary>Previous cluster drafts</summary>{drafts.map(item=><p key={item.id}><button className="ghostButton" disabled={busy} onClick={()=>open(item.id)}>{dateText(item.created_at)} · {item.result_memory_id?'accepted':'draft'}</button></p>)}</details>
  </section>;
}
