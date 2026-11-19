"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import LifecycleHistory from './LifecycleHistory';
import ActionGroup from './ActionGroup';

export default function ArchiveMemoryControl({ memory, onChange }: {
  memory: { id: string; archived_at?: string | null; updated_at: string; pinned?: boolean }; onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showArchive, setShowArchive] = useState(false);
  async function pin() {
    setBusy(true); setError('');
    try { await api(`/api/v1/memories/${memory.id}/pin`,{method:'POST',body:JSON.stringify({pinned:!memory.pinned,expected_updated_at:memory.updated_at})}); onChange(); }
    catch(e:any){setError(e.message);} finally{setBusy(false);}
  }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const reason = String(new FormData(e.currentTarget).get("reason") || "");
    setBusy(true); setError("");
    try {
      await api(`/api/v1/memories/${memory.id}/archive`, { method: "POST", body: JSON.stringify({
        archived: !memory.archived_at, expected_updated_at: memory.updated_at, reason,
      }) });
      onChange();
      setShowArchive(false);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <><section className="panel">
    <div className="panelHead"><h2>Memory actions</h2><ActionGroup label="Memory lifecycle actions">
      <button className="button" disabled={busy} aria-pressed={!!memory.pinned} onClick={pin}>{memory.pinned?'Unpin memory':'Pin memory'}</button>
      <button className="ghostButton" disabled={busy} aria-expanded={showArchive} aria-controls={`archive-${memory.id}`} onClick={()=>setShowArchive(!showArchive)}>{memory.archived_at?'Restore memory…':'Archive memory…'}</button>
    </ActionGroup></div>
    <p className="meta">Pinned memories keep their retrieval priority as they age. Archival, validity and project access still apply.</p>
    {showArchive&&<div id={`archive-${memory.id}`} className="archiveEditor">
    <p className="meta">Archiving excludes this memory from default search and AI context. Its content and history stay available; you can restore it here.</p>
    <form onSubmit={submit} className="archiveForm">
      <label htmlFor="archive-reason">Reason</label>
      <input id="archive-reason" className="input" name="reason" required minLength={3} maxLength={1000} placeholder="Why change its archival state?" />
      <button className="button" disabled={busy}>{busy ? "Saving…" : memory.archived_at ? "Restore memory" : "Archive memory"}</button>
    </form>
    </div>}
    {error && <p className="errorBox" role="alert">{error}</p>}
  </section><details className="historyDisclosure"><summary>Recent lifecycle actions & undo</summary><LifecycleHistory memoryId={memory.id} revision={memory.updated_at} onChange={onChange}/></details></>;
}
