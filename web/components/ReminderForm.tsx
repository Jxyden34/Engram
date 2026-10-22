"use client";
import {useState,FormEvent} from 'react';
import {api} from '@/lib/api';
export default function ReminderForm({memoryId,onSaved}:{memoryId:string,onSaved?:()=>void}){
 const [when,setWhen]=useState(''),[note,setNote]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 function quick(days:number){const d=new Date(Date.now()+days*86400000);d.setMinutes(d.getMinutes()-d.getTimezoneOffset());setWhen(d.toISOString().slice(0,16))}
 async function save(e:FormEvent){e.preventDefault();setBusy(true);try{await api('/api/v1/reminders',{method:'POST',body:JSON.stringify({memory_id:memoryId,due_at:new Date(when).toISOString(),note})});setMessage('Reminder saved. It will appear in Engram when due.');window.dispatchEvent(new Event('engram-reminders'));onSaved?.()}catch(e:any){setMessage(e.message)}finally{setBusy(false)}}
 return <form onSubmit={save} className="formGrid"><label className="field">Remind me at (your local time)<input className="input" type="datetime-local" required value={when} onChange={e=>setWhen(e.target.value)}/></label><div><button className="ghostButton" type="button" onClick={()=>quick(1)}>Tomorrow</button>{' '}<button className="ghostButton" type="button" onClick={()=>quick(7)}>In a week</button></div><label className="field">Note<input className="input" value={note} maxLength={1000} onChange={e=>setNote(e.target.value)} placeholder="What should you revisit?"/></label><button className="button" disabled={busy||!memoryId}>{busy?'Saving…':'Remind me'}</button>{message&&<p role="status">{message}</p>}</form>
}
